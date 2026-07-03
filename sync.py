import sys, os, re, csv, requests, anthropic
from markdownify import markdownify as md

CONF_EMAIL = os.environ.get("CONF_EMAIL")
CONF_TOKEN = os.environ.get("CONF_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
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

def load_glossary():
    xlsx_path = "Beamo_Glossary___Updated_2026-05-07-_01.xlsx"
    csv_path = "glossary.csv"
    
    if os.path.exists(xlsx_path):
        import openpyxl
        wb = openpyxl.load_workbook(xlsx_path, read_only=True)
        ws = wb['Beamo glossary']
        terms = []
        skip = {'shutter', 'General', None}
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or not row[0]:
                continue
            en = str(row[0]).strip().replace('\n', '')
            ja = str(row[2]).strip().replace('\n', '') if len(row) > 2 and row[2] else ''
            ko = str(row[3]).strip().replace('\n', '') if len(row) > 3 and row[3] else ''
            cat = str(row[4]).strip() if len(row) > 4 and row[4] else ''
            if en in skip or en == 'None':
                continue
            terms.append({'en': en, 'ko': ko, 'ja': ja, 'category': cat})
        print("용어집: 엑셀에서 " + str(len(terms)) + "개 로드됨")
        return terms
    elif os.path.exists(csv_path):
        with open(csv_path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    else:
        print("WARNING: 용어집 파일 없음")
        return []

def check_terms(text):
    issues = []
    checks = [
        ("Field Cam", "Field Camera"),
        ("Dollhouse View", "dollhouse view"),
        ("3D Workspace", "3d workspace"),
    ]
    for a, b in checks:
        if a in text and b.lower() in text.lower():
            issues.append("WARN: " + a + " / " + b + " 혼용 -> 통일 필요")
        else:
            issues.append("OK:   " + a + " 일관되게 사용 중")
    return issues

def translate(text, glossary, lang):
    lang_name = "Korean" if lang == "ko" else "Japanese"
    terms = "\n".join(t["en"] + " -> " + t[lang] for t in glossary if t.get(lang))
    prompt = "Translate this Markdown to " + lang_name + ". Keep all formatting. Use these terms exactly:\n" + terms + "\n\nDocument:\n" + text
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text

def save(title, lang, text):
    slug = re.sub(r'[^\w\-]', '-', title).strip('-')
    os.makedirs("output/" + lang, exist_ok=True)
    path = "output/" + lang + "/" + slug + ".md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print("저장: " + path)

def show_popup(report):
    msg = "=== 용어 검사 결과 ===\\n" + report + "\\n\\n번역 완료! output/en, ko, ja 폴더를 확인하세요."
    os.system("osascript -e 'display dialog \"" + msg + "\"'")

def main():
    url = sys.argv[1]
    print("[1/5] 페이지 ID 추출...")
    page_id = get_page_id(url)
    print("      ID: " + page_id)
    print("[2/5] Confluence 페이지 가져오는 중...")
    title, html = fetch_page(page_id)
    print("      제목: " + title)
    print("[3/5] Markdown 변환 중...")
    en_text = "# " + title + "\n\n" + md(html, heading_style="ATX")
    save(title, "en", en_text)
    print("[4/5] 용어 검사 중...")
    issues = check_terms(en_text)
    for i in issues:
        print(i)
    glossary = load_glossary()
    print("[5/5] 번역 중 (1~2분 소요)...")
    print("      -> 한국어...")
    save(title, "ko", translate(en_text, glossary, "ko"))
    print("      -> 일본어...")
    save(title, "ja", translate(en_text, glossary, "ja"))
    report = "\\n".join(issues)
    show_popup(report)

if __name__ == "__main__":
    main()