import sys, os, re, csv, subprocess, requests, anthropic
from markdownify import markdownify as md

# ===== 환경변수에서 읽어옴 (~/.zshrc에 export 되어 있음) =====
CONF_EMAIL = os.environ.get("CONF_EMAIL")
CONF_TOKEN = os.environ.get("CONF_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
# ==================================

GLOSSARY_FILE = "glossary.csv"

def get_page_id(url):
    match = re.search(r'/pages/(\d+)', url)
    return match.group(1) if match else sys.exit(1)

def fetch_page(page_id):
    r = requests.get(
        "https://3iai.atlassian.net/wiki/rest/api/content/" + page_id + "?expand=body.storage",
        auth=(CONF_EMAIL, CONF_TOKEN))
    d = r.json()
    if "title" not in d:
        print("API 응답:", d)
        sys.exit(1)
    return d["title"], d["body"]["storage"]["value"]

def fetch_attachments(page_id):
    r = requests.get(
        "https://3iai.atlassian.net/wiki/rest/api/content/" + page_id + "/child/attachment?limit=200",
        auth=(CONF_EMAIL, CONF_TOKEN))
    d = r.json()
    attachments = []
    for item in d.get("results", []):
        download_path = item.get("_links", {}).get("download")
        if not download_path:
            continue
        attachments.append({
            "filename": item["title"],
            "url": "https://3iai.atlassian.net/wiki" + download_path,
        })
    return attachments

def download_attachments(attachments, slug):
    folder = os.path.join("output", "images", slug)
    os.makedirs(folder, exist_ok=True)
    for att in attachments:
        r = requests.get(att["url"], auth=(CONF_EMAIL, CONF_TOKEN))
        path = os.path.join(folder, att["filename"])
        with open(path, "wb") as f:
            f.write(r.content)
        print("      이미지 저장: " + path)

def embed_images(html, slug, attachments):
    url_by_filename = {att["filename"]: att["url"] for att in attachments}
    def repl_attachment(m):
        filename = m.group(1)
        src = url_by_filename.get(filename, "../images/" + slug + "/" + filename)
        return '<img src="' + src + '" alt="' + filename + '"/>'
    html = re.sub(
        r'<ac:image[^>]*>\s*<ri:attachment ri:filename="([^"]+)"[^>]*/?>.*?</ac:image>',
        repl_attachment, html, flags=re.DOTALL)
    html = re.sub(
        r'<ac:image[^>]*>\s*<ri:url ri:value="([^"]+)"\s*/?>\s*</ac:image>',
        lambda m: '<img src="' + m.group(1) + '" alt="image"/>', html, flags=re.DOTALL)
    return html

def detect_language(text):
    sample = text[:500]
    ko_count = len(re.findall(r'[\uAC00-\uD7A3]', sample))
    ja_count = len(re.findall(r'[\u3040-\u30FF]', sample))
    en_count = len(re.findall(r'[a-zA-Z]', sample))
    if ko_count > 20:
        return "ko"
    elif ja_count > 20:
        return "ja"
    else:
        return "en"

def load_glossary():
    if not os.path.exists(GLOSSARY_FILE):
        print("WARNING: 용어집 파일 없음")
        return []
    terms = []
    with open(GLOSSARY_FILE, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            en = (row.get("Term (EN)") or "").strip()
            if not en or "▌" in en:
                continue
            terms.append({
                "en": en,
                "ko": (row.get("KR Glossary") or "").strip(),
                "ja": (row.get("JP Glossary") or "").strip(),
                "category": (row.get("Category") or "").strip(),
            })
    print("용어집: " + str(len(terms)) + "개 로드됨")
    return terms

def fix_terms(text, source_lang):
    if source_lang == "en":
        checks = [
            ("Field Cam", "Field Camera"),
            ("Dollhouse View", "dollhouse view"),
            ("3D Workspace", "3d workspace"),
        ]
    elif source_lang == "ko":
        checks = [
            ("필드 캠", "필드카메라"),
            ("돌하우스 뷰", "돌하우스뷰"),
            ("3D 워크스페이스", "3d 워크스페이스"),
        ]
    else:
        checks = []
    changes = []
    for canonical, variant in checks:
        pattern = re.compile(re.escape(variant), re.IGNORECASE)
        def repl(m, canonical=canonical):
            orig = m.group(0)
            if orig != canonical:
                changes.append(canonical + " <- \"" + orig + "\"")
            return canonical
        text = pattern.sub(repl, text)
    return text, changes

def translate(text, glossary, source_lang, target_lang):
    lang_names = {"en": "English", "ko": "Korean", "ja": "Japanese"}
    target_name = lang_names[target_lang]
    source_name = lang_names[source_lang]

    if source_lang == "en":
        terms = "\n".join(t["en"] + " -> " + t[target_lang] for t in glossary if t.get(target_lang))
    elif source_lang == "ko":
        terms = "\n".join(t["ko"] + " -> " + t[target_lang] for t in glossary if t.get("ko") and t.get(target_lang))
    else:
        terms = "\n".join(t["ja"] + " -> " + t[target_lang] for t in glossary if t.get("ja") and t.get(target_lang))

    images = []
    def stash(m):
        images.append(m.group(0))
        return "@@IMG" + str(len(images) - 1) + "@@"
    protected_text = re.sub(r'!\[[^\]]*\]\([^)]*\)', stash, text)

    prompt = "Translate this Markdown from " + source_name + " to " + target_name + ", preserving the original meaning, tone, and context. Keep all formatting. Do not translate, alter, remove, or reformat any @@IMGn@@ tokens - copy each one exactly as-is. Apply the following glossary terms wherever they naturally fit:\n" + terms + "\n\nDocument:\n" + protected_text

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": prompt}]
    result = ""
    for attempt in range(5):
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            messages=messages
        )
        chunk = msg.content[0].text
        result += chunk
        if msg.stop_reason != "max_tokens":
            break
        print("      (응답이 잘려서 이어서 생성 중... " + str(attempt + 1) + "회)")
        messages.append({"role": "assistant", "content": chunk})
        messages.append({"role": "user", "content": "Continue the translation from exactly where you stopped. Do not repeat any earlier text."})
    else:
        print("      WARNING: 5회 연속으로 잘림 - 결과가 불완전할 수 있음")

    for i, img in enumerate(images):
        result = result.replace("@@IMG" + str(i) + "@@", img)
    return result

def save_to_confluence(title, content, parent_id="2929229845"):
    import re as _re
    html = content
    html = _re.sub(r'^#### (.+)$', r'<h4>\1</h4>', html, flags=_re.MULTILINE)
    html = _re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=_re.MULTILINE)
    html = _re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=_re.MULTILINE)
    html = _re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=_re.MULTILINE)
    html = _re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = _re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    def convert_table(m):
        rows = [r.strip() for r in m.group(0).strip().split('\n') if r.strip() and not _re.match(r'^\|[-| :]+\|$', r.strip())]
        result = '<table><tbody>'
        for i, row in enumerate(rows):
            cells = [c.strip() for c in row.strip('|').split('|')]
            tag = 'th' if i == 0 else 'td'
            result += '<tr>' + ''.join('<' + tag + '>' + c + '</' + tag + '>' for c in cells) + '</tr>'
        result += '</tbody></table>'
        return result
    html = _re.sub(r'(\|.+\|\n)+', convert_table, html)
    html = _re.sub(r'^\* (.+)$', r'<li>\1</li>', html, flags=_re.MULTILINE)
    html = _re.sub(r'(<li>.*</li>\n?)+', lambda m: '<ul>' + m.group(0) + '</ul>', html)
    html = _re.sub(r'^\d+\. (.+)$', r'<li>\1</li>', html, flags=_re.MULTILINE)
    html = _re.sub(r'\n\n', '</p><p>', html)
    html = '<p>' + html + '</p>'

    url = "https://3iai.atlassian.net/wiki/rest/api/content"
    data = {
        "type": "page",
        "title": title,
        "ancestors": [{"id": parent_id}],
        "space": {"key": "B3EUM"},
        "body": {
            "storage": {
                "value": html,
                "representation": "storage"
            }
        }
    }
    r = requests.post(url, json=data, auth=(CONF_EMAIL, CONF_TOKEN),
                      headers={"Content-Type": "application/json"})
    if r.status_code == 200:
        print("      Confluence 저장 완료: " + title)
    else:
        print("      Confluence 저장 실패: " + str(r.status_code) + " " + r.text[:100])

def slugify(title):
    return re.sub(r'[^\w\-]', '-', title).strip('-')

def save(title, lang, text):
    slug = slugify(title)
    os.makedirs("output/" + lang, exist_ok=True)
    path = "output/" + lang + "/" + slug + ".md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print("저장: " + path)

def show_popup(report, source_lang):
    lang_label = {"en": "영어", "ko": "한국어", "ja": "일본어"}
    msg = "원본 언어: " + lang_label.get(source_lang, source_lang) + "\n=== 용어 검사 결과 ===\n" + report + "\n\n번역 완료! output 폴더를 확인하세요."
    escaped = msg.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    subprocess.run(["osascript", "-e", 'display dialog "' + escaped + '"'])

def main():
    url = sys.argv[1]
    print("[1/5] 페이지 ID 추출...")
    page_id = get_page_id(url)
    print("      ID: " + page_id)

    print("[2/5] Confluence 페이지 가져오는 중...")
    title, html = fetch_page(page_id)
    slug = slugify(title)
    print("      제목: " + title)
    attachments = fetch_attachments(page_id)
    if attachments:
        print("      이미지 " + str(len(attachments)) + "개 발견, 다운로드 중...")
        download_attachments(attachments, slug)
        html = embed_images(html, slug, attachments)
    else:
        print("      첨부 이미지 없음")

    print("[3/5] Markdown 변환 중...")
    source_text = "# " + title + "\n\n" + md(html, heading_style="ATX")

    source_lang = detect_language(source_text)
    lang_label = {"en": "영어", "ko": "한국어", "ja": "일본어"}
    print("      감지된 언어: " + lang_label.get(source_lang, source_lang))

    print("[4/5] 용어 통일 중...")
    source_text, fixes = fix_terms(source_text, source_lang)
    if fixes:
        for f in fixes:
            print("FIXED: " + f)
    else:
        print("OK:   용어 혼용 없음")
    save(title, source_lang, source_text)

    glossary = load_glossary()
    target_langs = [l for l in ["en", "ko", "ja"] if l != source_lang]

    print("[5/5] 번역 중 (1~2분 소요)...")
    for target_lang in target_langs:
        lang_name = {"en": "영어", "ko": "한국어", "ja": "일본어"}[target_lang]
        print("      -> " + lang_name + "...")
        translated = translate(source_text, glossary, source_lang, target_lang)
        save(title, target_lang, translated)
        conf_title = "[" + target_lang.upper() + "] " + title
        print("      Confluence에 " + lang_name + " 저장 중...")
        save_to_confluence(conf_title, translated, "2929229845")

    report = "\n".join(fixes) if fixes else "용어 혼용 없음"
    show_popup(report, source_lang)

if __name__ == "__main__":
    main()