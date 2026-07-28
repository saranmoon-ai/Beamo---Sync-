import sys, os, re, json, argparse, subprocess, requests
from sync import (
    CONF_EMAIL, CONF_TOKEN,
    get_page_id, fetch_page, fetch_attachments, detect_language, load_glossary, fix_terms,
)
from publish_confluence import (
    protect_macros, restore_macros, call_translation_api,
    find_child_page, PARENT_PAGE_ID, SPACE_KEY,
)

# GitHub Actions는 이 환경변수를 자동으로 "true"로 설정함.
# 로컬(Mac, Automator 버튼)에서는 없으므로 False.
CI_MODE = os.environ.get("GITHUB_ACTIONS") == "true"

AX_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.environ.get("SITE_DIR", "/Users/3i-a1-2021-300/Desktop/Beamo manual website")
SITE_ARTICLES_DIR = os.path.join(SITE_DIR, "content", "articles")
SITE_IMAGES_DIR = os.path.join(SITE_DIR, "images")
PAGE_MAP_FILE = os.path.join(AX_DIR, "page_map.json")

LANG_LABEL = {"en": "영어", "ko": "한국어", "ja": "일본어"}
LANG_NAME = {"en": "English", "ko": "Korean", "ja": "Japanese"}

KNOWN_FEATURES = ["getting-started", "survey", "3d-workspace", "admin", "appendix", "whats-new"]
KNOWN_VERSIONS = ["3.0", "2.0"]
KNOWN_PLATFORMS = ["web", "aos", "ios"]
KNOWN_USERS = ["all", "surveyor", "team-admin", "collaborator", "site-manager", "super-admin"]


# ===== 신규 문서 분류 정보 입력 폼 (한 창에서 전부 입력 후 한 번에 제출) =====

def ask_metadata_form(page_title):
    import tkinter as tk
    from tkinter import ttk, messagebox

    result = {}
    root = tk.Tk()
    root.title("Beamo 매뉴얼 - 웹사이트 분류 정보")
    root.attributes("-topmost", True)
    root.resizable(False, False)
    pad = {"padx": 12, "pady": 6}

    tk.Label(root, text="새 문서: " + page_title, font=("", 12, "bold"),
             wraplength=380, justify="left").grid(row=0, column=0, columnspan=2, sticky="w", **pad)

    tk.Label(root, text="카테고리").grid(row=1, column=0, sticky="w", **pad)
    feature_var = tk.StringVar(value=KNOWN_FEATURES[0])
    ttk.Combobox(root, textvariable=feature_var, values=KNOWN_FEATURES,
                 state="readonly", width=25).grid(row=1, column=1, sticky="w", **pad)

    custom_feature_var = tk.StringVar()
    tk.Label(root, text="(목록에 없으면 여기 직접 입력)").grid(row=2, column=0, sticky="w", padx=12)
    tk.Entry(root, textvariable=custom_feature_var, width=27).grid(row=2, column=1, sticky="w", padx=12)

    tk.Label(root, text="버전").grid(row=3, column=0, sticky="w", **pad)
    version_var = tk.StringVar(value=KNOWN_VERSIONS[0])
    ttk.Combobox(root, textvariable=version_var, values=KNOWN_VERSIONS,
                 state="readonly", width=25).grid(row=3, column=1, sticky="w", **pad)

    tk.Label(root, text="플랫폼 (복수 선택)").grid(row=4, column=0, sticky="nw", **pad)
    platform_vars = {}
    pf_frame = tk.Frame(root)
    pf_frame.grid(row=4, column=1, sticky="w", **pad)
    for i, p in enumerate(KNOWN_PLATFORMS):
        v = tk.BooleanVar(value=(p == "web"))
        tk.Checkbutton(pf_frame, text=p, variable=v).grid(row=0, column=i, sticky="w")
        platform_vars[p] = v

    tk.Label(root, text="대상 사용자 (복수 선택)").grid(row=5, column=0, sticky="nw", **pad)
    user_vars = {}
    us_frame = tk.Frame(root)
    us_frame.grid(row=5, column=1, sticky="w", **pad)
    for i, u in enumerate(KNOWN_USERS):
        v = tk.BooleanVar(value=(u == "all"))
        tk.Checkbutton(us_frame, text=u, variable=v).grid(row=i // 3, column=i % 3, sticky="w")
        user_vars[u] = v

    tk.Label(root, text="스텝(챕터) 번호").grid(row=6, column=0, sticky="w", **pad)
    step_var = tk.StringVar(value="1")
    tk.Entry(root, textvariable=step_var, width=10).grid(row=6, column=1, sticky="w", **pad)

    def on_submit():
        feature = custom_feature_var.get().strip() or feature_var.get()
        platforms = [p for p, v in platform_vars.items() if v.get()]
        users = [u for u, v in user_vars.items() if v.get()]
        step_text = step_var.get().strip()
        if not platforms:
            messagebox.showerror("오류", "플랫폼을 하나 이상 선택하세요.")
            return
        if not users:
            messagebox.showerror("오류", "대상 사용자를 하나 이상 선택하세요.")
            return
        if not step_text.isdigit():
            messagebox.showerror("오류", "스텝 번호는 숫자로 입력하세요.")
            return
        result["feature"] = feature
        result["version"] = version_var.get()
        result["platform"] = platforms
        result["user"] = users
        result["step"] = int(step_text)
        root.destroy()

    btn_frame = tk.Frame(root)
    btn_frame.grid(row=7, column=0, columnspan=2, pady=12)
    tk.Button(btn_frame, text="취소", width=10, command=root.destroy).grid(row=0, column=0, padx=6)
    tk.Button(btn_frame, text="제출", width=10, command=on_submit).grid(row=0, column=1, padx=6)

    root.lift()
    root.focus_force()
    root.mainloop()
    return result or None


def show_summary_popup(key, title, source_lang, target_langs, fixes, committed, extra_lines=None):
    lines = [
        "문서: " + title,
        "웹사이트 항목: " + key,
        "원본 언어: " + LANG_LABEL.get(source_lang, source_lang),
        "번역됨: " + ", ".join(LANG_LABEL.get(l, l) for l in target_langs),
        "",
        "용어 통일: " + (", ".join(fixes) if fixes else "없음"),
        "",
    ]
    if extra_lines:
        lines.extend(extra_lines)
    elif committed:
        lines.append("웹사이트 파일이 로컬에 커밋되었습니다.")
        lines.append("index.html이 브라우저에 열렸으니 확인 후, 문제 없으면 직접 git push 해주세요.")
    else:
        lines.append("변경사항이 없어 커밋하지 않았습니다.")
    msg = "\n".join(lines)

    if CI_MODE:
        print(msg)
        summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_file:
            with open(summary_file, "a", encoding="utf-8") as f:
                f.write("## Beamo 매뉴얼 번역 결과\n\n" + "\n".join("- " + l for l in lines if l) + "\n")
        return

    escaped = msg.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    subprocess.run(["osascript", "-e", 'display dialog "' + escaped + '" with title "Beamo 매뉴얼 업데이트 완료"'])


# ===== page_map.json (컨플루언스 페이지 <-> 웹사이트 항목 매핑) =====

def load_page_map():
    if not os.path.exists(PAGE_MAP_FILE):
        return {}
    with open(PAGE_MAP_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_page_map(m):
    with open(PAGE_MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)


def next_key_and_order(arr, step):
    prefix = "s" + str(step) + "-"
    local_idx = [int(a["key"][len(prefix):]) for a in arr
                 if a.get("key", "").startswith(prefix) and a["key"][len(prefix):].isdigit()]
    next_local = (max(local_idx) + 1) if local_idx else 1
    key = prefix + str(next_local)
    next_order = max((a.get("order", 0) for a in arr), default=0) + 1
    return key, next_order


def get_or_create_mapping(page_id, page_title, cli_meta=None):
    page_map = load_page_map()
    if page_id in page_map:
        mapping = page_map[page_id]
        mapping.setdefault("confluence_page_ids", {})
        return mapping, False

    if CI_MODE:
        print("      새 문서입니다. 입력된 분류 정보를 사용합니다...")
        missing = [k for k in ("feature", "version", "platform", "user", "step") if not cli_meta or not cli_meta.get(k)]
        if missing:
            sys.exit("새 문서인데 분류 정보가 부족합니다 (누락: " + ", ".join(missing) + "). "
                      "워크플로 실행 시 feature/version/platform/user/step을 모두 입력해주세요.")
        answers = cli_meta
    else:
        print("      새 문서입니다. 웹사이트 분류 정보 입력 창을 띄웁니다...")
        answers = ask_metadata_form(page_title)
        if answers is None:
            sys.exit("사용자가 취소했습니다.")

    arr = load_site_articles()
    key, order = next_key_and_order(arr, answers["step"])

    mapping = {
        "key": key,
        "version": answers["version"],
        "platform": answers["platform"],
        "feature": answers["feature"],
        "user": answers["user"],
        "step": answers["step"],
        "order": order,
        "confluence_page_ids": {},
    }
    page_map[page_id] = mapping
    save_page_map(page_map)
    return mapping, True


def save_mapping(page_id, mapping):
    page_map = load_page_map()
    page_map[page_id] = mapping
    save_page_map(page_map)


# ===== 컨플루언스 내부 링크(<ac:link>) -> 사이트 문서 key 해석 =====

_page_id_by_title_cache = {}


def find_page_id_by_title(title, space_key=SPACE_KEY):
    """컨플루언스 페이지 제목으로 페이지 ID를 검색 (같은 스페이스 내). API 호출 결과는 캐시."""
    if title in _page_id_by_title_cache:
        return _page_id_by_title_cache[title]
    r = requests.get(
        CONF_CONTENT_API.rstrip("/"),
        params={"title": title, "spaceKey": space_key, "type": "page", "limit": 1},
        auth=(CONF_EMAIL, CONF_TOKEN))
    results = r.json().get("results", []) if r.status_code == 200 else []
    page_id = results[0]["id"] if results else None
    _page_id_by_title_cache[title] = page_id
    return page_id


def find_site_key_by_confluence_id(conf_page_id, page_map):
    """page_map.json에서 컨플루언스 페이지 ID(원본 또는 번역본)에 대응하는 사이트 문서 key를 찾음."""
    if not conf_page_id:
        return None
    if conf_page_id in page_map:
        return page_map[conf_page_id]["key"]
    for mapping in page_map.values():
        if conf_page_id in mapping.get("confluence_page_ids", {}).values():
            return mapping["key"]
    return None


# ===== content/articles/<key>.json 읽기/쓰기 =====
# content-data.js는 더 이상 이 스크립트가 직접 쓰지 않는다 - 문서별 JSON 파일이
# 진짜 소스이고, content-data.js는 GitHub Actions 빌드가 그걸 읽어 재생성하는
# 산출물이다 (Decap CMS 쪽 편집도 같은 문서별 JSON 파일을 대상으로 하므로,
# 두 경로가 항상 같은 소스를 공유한다).

def load_site_articles():
    """전체 문서 목록 (다음 key/order 계산용으로만 사용)."""
    arr = []
    if not os.path.isdir(SITE_ARTICLES_DIR):
        return arr
    for filename in sorted(os.listdir(SITE_ARTICLES_DIR)):
        if not filename.endswith(".json"):
            continue
        with open(os.path.join(SITE_ARTICLES_DIR, filename), encoding="utf-8") as f:
            arr.append(json.load(f))
    return arr


def load_one_article(key):
    path = os.path.join(SITE_ARTICLES_DIR, key + ".json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_one_article(article):
    os.makedirs(SITE_ARTICLES_DIR, exist_ok=True)
    path = os.path.join(SITE_ARTICLES_DIR, article["key"] + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(article, f, ensure_ascii=False, indent=2)
        f.write("\n")


def update_site_content(mapping, site_i18n):
    key = mapping["key"]
    existing = load_one_article(key)
    if existing is None:
        existing = {
            "key": key,
            "version": mapping["version"],
            "platform": mapping["platform"],
            "feature": mapping["feature"],
            "user": mapping["user"],
            "step": mapping["step"],
            "order": mapping["order"],
            "i18n": {},
        }
    existing["i18n"].update(site_i18n)
    save_one_article(existing)


# ===== 이미지 다운로드 (웹사이트 images 폴더로) =====

def slugify_filename(filename):
    base, ext = os.path.splitext(filename)
    base = re.sub(r'[^a-zA-Z0-9]+', '-', base).strip('-').lower()
    return (base or "image") + ext.lower()


def download_site_image(url, key, filename):
    folder = os.path.join(SITE_IMAGES_DIR, key)
    os.makedirs(folder, exist_ok=True)
    local_name = slugify_filename(filename)
    path = os.path.join(folder, local_name)
    if not os.path.exists(path):
        r = requests.get(url, auth=(CONF_EMAIL, CONF_TOKEN))
        with open(path, "wb") as f:
            f.write(r.content)
    return "images/" + key + "/" + local_name


# ===== Confluence storage HTML -> 사이트용 순수 HTML =====

def storage_html_to_site_html(html, attachments, key, page_map):
    url_by_filename = {att["filename"]: att["url"] for att in attachments}

    html = re.sub(r'<ac:inline-comment-marker[^>]*>(.*?)</ac:inline-comment-marker>', r'\1', html, flags=re.DOTALL)
    html = re.sub(r'<ac:structured-macro ac:name="toc".*?</ac:structured-macro>', '', html, flags=re.DOTALL)

    def repl_attachment_image(m):
        filename = m.group(1)
        url = url_by_filename.get(filename)
        if not url:
            return ''
        local_src = download_site_image(url, key, filename)
        return '<img src="' + local_src + '" alt="' + filename + '">'

    html = re.sub(
        r'<ac:image[^>]*>\s*<ri:attachment ri:filename="([^"]+)"[^>]*/?>.*?</ac:image>',
        repl_attachment_image, html, flags=re.DOTALL)
    html = re.sub(
        r'<ac:image[^>]*>\s*<ri:url ri:value="([^"]+)"\s*/?>\s*</ac:image>',
        lambda m: '<img src="' + m.group(1) + '" alt="image">', html, flags=re.DOTALL)

    def repl_link(m):
        block = m.group(0)
        body_match = re.search(
            r'<ac:(?:plain-text-link-body|link-body)>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</ac:(?:plain-text-link-body|link-body)>',
            block, flags=re.DOTALL)
        text = body_match.group(1) if body_match else ''
        if not text:
            return ''

        is_page_ref = bool(re.search(r'<ri:page\b', block))

        # 1) ri:content-id가 있으면 바로 사용 (API 호출 불필요)
        id_match = re.search(r'<ri:page\b[^>]*\bri:content-id="(\d+)"', block)
        conf_page_id = id_match.group(1) if id_match else None

        # 2) 없으면 ri:content-title로 페이지 ID를 검색
        if not conf_page_id:
            title_match = re.search(r'<ri:page\b[^>]*\bri:content-title="([^"]+)"', block)
            if title_match:
                target_title = title_match.group(1).replace("&amp;", "&")
                conf_page_id = find_page_id_by_title(target_title)

        site_key = find_site_key_by_confluence_id(conf_page_id, page_map)
        if site_key:
            return '<a href="javascript:void(0)" data-goto-key="' + site_key + '">' + text + '</a>'

        if is_page_ref:
            print("      WARNING: 링크 대상 문서가 아직 사이트에 없어 텍스트만 유지함: \"" + text + "\"")
        return text

    html = re.sub(r'<ac:link.*?</ac:link>', repl_link, html, flags=re.DOTALL)

    def repl_macro(m):
        body_match = re.search(r'<ac:rich-text-body>(.*?)</ac:rich-text-body>', m.group(0), flags=re.DOTALL)
        return '<blockquote>' + body_match.group(1) + '</blockquote>' if body_match else ''

    html = re.sub(r'<ac:structured-macro.*?</ac:structured-macro>', repl_macro, html, flags=re.DOTALL)
    return html


# ===== 번역 (언어 무관 - en/ko/ja 어느 방향이든 지원) =====

def build_glossary_terms(glossary, source_lang, target_lang):
    return "\n".join(
        t[source_lang] + " -> " + t[target_lang]
        for t in glossary if t.get(source_lang) and t.get(target_lang)
    )


def translate_html_site(protected_html, glossary, source_lang, target_lang):
    terms = build_glossary_terms(glossary, source_lang, target_lang)
    prompt = (
        "The following is Confluence storage-format HTML/XML content. Some parts have been replaced "
        "with opaque placeholder tokens like @@PH0@@, @@PH1@@ - copy every placeholder token exactly "
        "as-is, do not translate, alter, or remove them. Translate ONLY the human-readable text into "
        + LANG_NAME[target_lang] + ", preserving the original meaning, tone, and context above all else. "
        "Keep every HTML/XML tag exactly as-is - do not add, remove, or modify any tag or attribute. Apply "
        "the following glossary terms wherever they naturally fit; if a term would make a sentence awkward "
        "or grammatically incorrect, prioritize natural, correct phrasing over strict term matching:\n"
        + terms + "\n\nContent:\n" + protected_html
    )
    return call_translation_api(prompt)


def translate_title_site(title, glossary, source_lang, target_lang):
    terms = build_glossary_terms(glossary, source_lang, target_lang)
    prompt = (
        "Translate this Confluence page title to " + LANG_NAME[target_lang] + ". Return ONLY the translated "
        "title, nothing else - no quotes, no explanation. Apply these glossary terms wherever they fit:\n"
        + terms + "\n\nTitle: " + title
    )
    return call_translation_api(prompt).strip()


# ===== Confluence 게시 (제목이 아니라 저장된 페이지 ID로 갱신 - 제목이 매번 조금씩 다르게 번역돼도 중복 생성 방지) =====

CONF_CONTENT_API = "https://3iai.atlassian.net/wiki/rest/api/content/"


def publish_page_tracked(parent_id, space_key, title, html, known_id):
    existing_id = known_id or find_child_page(parent_id, title)
    if existing_id:
        r = requests.get(CONF_CONTENT_API + existing_id, params={"expand": "version"},
                          auth=(CONF_EMAIL, CONF_TOKEN))
        version = r.json()["version"]["number"]
        body = {
            "id": existing_id,
            "type": "page",
            "title": title,
            "version": {"number": version + 1},
            "body": {"storage": {"value": html, "representation": "storage"}},
        }
        r = requests.put(CONF_CONTENT_API + existing_id, json=body, auth=(CONF_EMAIL, CONF_TOKEN))
    else:
        body = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "ancestors": [{"id": parent_id}],
            "body": {"storage": {"value": html, "representation": "storage"}},
        }
        r = requests.post(CONF_CONTENT_API, json=body, auth=(CONF_EMAIL, CONF_TOKEN))

    if r.status_code not in (200, 201):
        print("      ERROR: 컨플루언스 게시 실패 (" + str(r.status_code) + "): " + r.text[:300])
        return existing_id
    return r.json().get("id")


# ===== git =====

def git_commit_site(key, title):
    """로컬(Mac) 모드: 현재 브랜치에 커밋만 함. push는 사용자가 직접."""
    subprocess.run(["git", "add", "content/articles", "images"], cwd=SITE_DIR)
    msg = "자동 번역 반영: " + key + " - " + title
    r = subprocess.run(["git", "commit", "-m", msg], cwd=SITE_DIR, capture_output=True, text=True)
    return r.returncode == 0


def git_commit_site_ci(key, title, page_id):
    """CI 모드: 새 브랜치를 만들어 커밋 + push 후 PR을 연다. PR URL(또는 None)을 반환."""
    branch = "translate/" + key + "-" + page_id
    subprocess.run(["git", "checkout", "-b", branch], cwd=SITE_DIR, check=True)
    subprocess.run(["git", "add", "content/articles", "images"], cwd=SITE_DIR)
    msg = "자동 번역 반영: " + key + " - " + title
    r = subprocess.run(["git", "commit", "-m", msg], cwd=SITE_DIR, capture_output=True, text=True)
    if r.returncode != 0:
        print("      변경사항이 없어 커밋하지 않았습니다.")
        return None

    subprocess.run(["git", "push", "-u", "origin", branch], cwd=SITE_DIR, check=True)

    r = subprocess.run(
        ["gh", "pr", "create", "--title", msg, "--body",
         "컨플루언스 문서 [" + title + "](" + CONF_CONTENT_API + page_id + ") 자동 번역/등록 결과입니다.\n\n"
         "병합 전에 index.html 미리보기나 GitHub Pages 프리뷰로 내용을 확인해주세요.",
         "--head", branch],
        cwd=SITE_DIR, capture_output=True, text=True)
    if r.returncode != 0:
        print("      WARNING: PR 생성 실패: " + r.stderr.strip())
        return None
    return r.stdout.strip()


def sync_repo_commit_page_map(key, title):
    """CI 모드에서 새 문서 매핑이 생겼을 때, page_map.json을 Sync 저장소(main)에 바로 커밋+push."""
    r = subprocess.run(["git", "diff", "--quiet", "page_map.json"], cwd=AX_DIR)
    if r.returncode == 0:
        return  # 변경 없음
    subprocess.run(["git", "add", "page_map.json"], cwd=AX_DIR, check=True)
    msg = "새 문서 매핑 추가: " + key + " - " + title
    subprocess.run(["git", "commit", "-m", msg], cwd=AX_DIR, check=True)
    subprocess.run(["git", "push"], cwd=AX_DIR, check=True)


def open_site_preview():
    if CI_MODE:
        return
    subprocess.run(["open", os.path.join(SITE_DIR, "index.html")])


# ===== main =====

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Confluence 페이지 URL")
    parser.add_argument("--feature")
    parser.add_argument("--version")
    parser.add_argument("--platform", help="쉼표로 구분 (예: web,aos)")
    parser.add_argument("--user", help="쉼표로 구분 (예: all,surveyor)")
    parser.add_argument("--step", type=int)
    return parser.parse_args()


def main():
    args = parse_args()
    url = args.url
    cli_meta = None
    if args.feature or args.version or args.platform or args.user or args.step:
        cli_meta = {
            "feature": args.feature,
            "version": args.version,
            "platform": [p.strip() for p in args.platform.split(",")] if args.platform else None,
            "user": [u.strip() for u in args.user.split(",")] if args.user else None,
            "step": args.step,
        }

    print("[1/6] 페이지 ID 추출...")
    page_id = get_page_id(url)
    print("      ID: " + page_id)

    print("[2/6] Confluence 원본 가져오는 중...")
    title, html = fetch_page(page_id)
    print("      제목: " + title)
    attachments = fetch_attachments(page_id)
    glossary = load_glossary()

    plain_text = re.sub(r'<[^>]+>', ' ', html)
    source_lang = detect_language(title + " " + plain_text)
    print("      감지된 언어: " + LANG_LABEL.get(source_lang, source_lang))

    print("[3/6] 용어 통일 중...")
    html, fixes = fix_terms(html, source_lang)
    for f in fixes:
        print("      FIXED: " + f)

    print("[4/6] 웹사이트 항목 확인 중...")
    mapping, is_new = get_or_create_mapping(page_id, title, cli_meta)
    key = mapping["key"]
    print("      항목 key: " + key)
    if CI_MODE and is_new:
        sync_repo_commit_page_map(key, title)
    page_map = load_page_map()  # 다른 문서로의 내부 링크(data-goto-key) 해석에 사용

    print("[5/6] 매크로 보호 및 번역 중...")
    protected_html, placeholders = protect_macros(html, attachments)
    target_langs = [l for l in ("en", "ko", "ja") if l != source_lang]

    site_i18n = {
        source_lang: {
            "title": title,
            "html": storage_html_to_site_html(restore_macros(protected_html, placeholders), attachments, key, page_map),
        }
    }

    for lang in target_langs:
        lang_name = LANG_LABEL.get(lang, lang)
        print("      -> " + lang_name + " 번역 중...")
        translated_storage_html = restore_macros(
            translate_html_site(protected_html, glossary, source_lang, lang), placeholders)
        translated_title = translate_title_site(title, glossary, source_lang, lang)
        site_i18n[lang] = {
            "title": translated_title,
            "html": storage_html_to_site_html(translated_storage_html, attachments, key, page_map),
        }
        if lang in PARENT_PAGE_ID:
            print("      컨플루언스에 " + lang_name + " 게시 중...")
            known_id = mapping["confluence_page_ids"].get(lang)
            new_id = publish_page_tracked(
                PARENT_PAGE_ID[lang], SPACE_KEY, translated_title, translated_storage_html, known_id)
            if new_id:
                mapping["confluence_page_ids"][lang] = new_id
                save_mapping(page_id, mapping)
        else:
            print("      (" + lang_name + "용 컨플루언스 상위 페이지가 없어 컨플루언스 게시는 건너뜀)")

    print("[6/6] 웹사이트 파일 갱신 및 커밋 중...")
    update_site_content(mapping, site_i18n)

    if CI_MODE:
        pr_url = git_commit_site_ci(key, title, page_id)
        extra = ["PR: " + pr_url] if pr_url else ["변경사항이 없어 PR을 만들지 않았습니다."]
        show_summary_popup(key, title, source_lang, target_langs, fixes, bool(pr_url), extra_lines=extra)
    else:
        committed = git_commit_site(key, title)
        open_site_preview()
        show_summary_popup(key, title, source_lang, target_langs, fixes, committed)


if __name__ == "__main__":
    main()
