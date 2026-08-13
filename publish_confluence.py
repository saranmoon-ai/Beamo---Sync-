import sys, re, requests, anthropic
from sync import (
    CONF_EMAIL, CONF_TOKEN, ANTHROPIC_API_KEY,
    get_page_id, fetch_page, fetch_attachments, load_glossary,
)

# ===== 게시 대상 (언어별 상위 페이지) =====
PARENT_PAGE_ID = {
    "ko": "2929918015",  # [Beamo 3.0] 사용자 매뉴얼 _한국어
    "ja": "2929197130",  # [Beamo 3.0]使用者マニュアル＿日本語
}
SPACE_KEY = "B3EUM"
# =========================================


# ===== Output log parent (백업/로그 저장용 상위 페이지) =====
OUTPUT_LOG_PARENT_ID = "2948988954"  # "Output folder" (스페이스 B3EUM)
# ============================================================


def call_translation_api(prompt):
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
        messages.append({"role": "user", "content": "Continue exactly where you left off. Do not repeat any earlier text."})
    else:
        print("      WARNING: 5회 연속으로 잘림 - 결과가 불완전할 수 있음")
    return result


def protect_macros(html, attachments):
    """이미지(width 포함)/링크/매크로처럼 번역하면 깨지는 부분을 플레이스홀더로 치환.
    ac:rich-text-body를 가진 매크로(info/note 등)는 본문만 번역 대상으로 남겨둠."""
    url_by_filename = {att["filename"]: att["url"] for att in attachments}
    placeholders = []

    def stash(content):
        placeholders.append(content)
        return "@@PH" + str(len(placeholders) - 1) + "@@"

    def repl_image_attachment(m):
        block = m.group(0)
        filename = m.group(1)
        width_match = re.search(r'ac:width="(\d+)"', block)
        width_attr = ' ac:width="' + width_match.group(1) + '"' if width_match else ''
        url = url_by_filename.get(filename)
        if url:
            safe_url = url.replace("&", "&amp;")
            rebuilt = ('<ac:image ac:align="center" ac:layout="center"' + width_attr +
                       '><ri:url ri:value="' + safe_url + '"/></ac:image>')
        else:
            rebuilt = block
        return stash(rebuilt)

    html = re.sub(
        r'<ac:image[^>]*>\s*<ri:attachment ri:filename="([^"]+)"[^>]*/?>.*?</ac:image>',
        repl_image_attachment, html, flags=re.DOTALL)
    html = re.sub(
        r'<ac:image[^>]*>\s*<ri:url[^>]*/?>\s*</ac:image>',
        lambda m: stash(m.group(0)), html, flags=re.DOTALL)

    # 내부 페이지 링크: 대상(ri:page/ri:attachment)만 보호하고, 링크 텍스트는 번역되도록 남겨둠
    # (예전에는 <ac:link> 전체를 통째로 보호해서 링크 텍스트가 번역 안 되는 한계가 있었음 - 수정됨)
    link_text_re = re.compile(
        r'(<ac:link\b.*?<ac:(?:plain-text-link-body|link-body)>(?:<!\[CDATA\[)?)'
        r'(.*?)'
        r'((?:\]\]>)?</ac:(?:plain-text-link-body|link-body)>.*?</ac:link>)',
        re.DOTALL)

    def repl_ac_link(m):
        block = m.group(0)
        inner = link_text_re.match(block)
        if not inner:
            return stash(block)  # 텍스트 본문이 없는 링크(예: 이미지 전용) - 통째로 보호
        prefix, text, suffix = inner.group(1), inner.group(2), inner.group(3)
        return stash(prefix) + text + stash(suffix)

    html = re.sub(r'<ac:link\b.*?</ac:link>', repl_ac_link, html, flags=re.DOTALL)

    # 인라인 코멘트 마커: 래퍼만 벗기고 안의 텍스트는 번역 대상으로 남김
    html = re.sub(r'<ac:inline-comment-marker[^>]*>(.*?)</ac:inline-comment-marker>', r'\1', html, flags=re.DOTALL)

    def repl_structured_macro(m):
        block = m.group(0)
        rtb_match = re.search(r'<ac:rich-text-body>(.*?)</ac:rich-text-body>', block, flags=re.DOTALL)
        if rtb_match:
            body = rtb_match.group(1)
            prefix = block[:rtb_match.start()]
            suffix = block[rtb_match.end():]
            return stash(prefix + "<ac:rich-text-body>") + body + stash("</ac:rich-text-body>" + suffix)
        return stash(block)

    html = re.sub(r'<ac:structured-macro.*?</ac:structured-macro>', repl_structured_macro, html, flags=re.DOTALL)

    return html, placeholders


def restore_macros(text, placeholders):
    for i, content in enumerate(placeholders):
        text = text.replace("@@PH" + str(i) + "@@", content)
    return text


def translate_html(protected_html, glossary, lang):
    lang_name = "Korean" if lang == "ko" else "Japanese"
    terms = "\n".join(t["en"] + " -> " + t[lang] for t in glossary if t.get(lang))
    prompt = (
        "The following is Confluence storage-format HTML/XML content. Some parts have been replaced "
        "with opaque placeholder tokens like @@PH0@@, @@PH1@@ - copy every placeholder token exactly "
        "as-is, do not translate, alter, or remove them. Translate ONLY the human-readable text into "
        + lang_name + ", preserving the original meaning, tone, and context above all else. Keep every "
        "HTML/XML tag exactly as-is - do not add, remove, or modify any tag or attribute. Apply the "
        "following glossary terms wherever they naturally fit; if a term would make a sentence awkward "
        "or grammatically incorrect, prioritize natural, correct phrasing over strict term matching:\n"
        + terms + "\n\nContent:\n" + protected_html
    )
    return call_translation_api(prompt)


def translate_title(title, glossary, lang):
    lang_name = "Korean" if lang == "ko" else "Japanese"
    terms = "\n".join(t["en"] + " -> " + t[lang] for t in glossary if t.get(lang))
    prompt = (
        "Translate this Confluence page title to " + lang_name + ". Return ONLY the translated title, "
        "nothing else - no quotes, no explanation. Apply these glossary terms wherever they fit:\n"
        + terms + "\n\nTitle: " + title
    )
    return call_translation_api(prompt).strip()


def find_child_page(parent_id, title):
    r = requests.get(
        "https://3iai.atlassian.net/wiki/rest/api/content/" + parent_id + "/child/page",
        params={"limit": 100},
        auth=(CONF_EMAIL, CONF_TOKEN))
    for item in r.json().get("results", []):
        if item["title"] == title:
            return item["id"]
    return None


def publish_page(parent_id, space_key, title, html):
    existing_id = find_child_page(parent_id, title)
    if existing_id:
        r = requests.get(
            "https://3iai.atlassian.net/wiki/rest/api/content/" + existing_id + "?expand=version",
            auth=(CONF_EMAIL, CONF_TOKEN))
        version = r.json()["version"]["number"]
        body = {
            "id": existing_id,
            "type": "page",
            "title": title,
            "version": {"number": version + 1},
            "body": {"storage": {"value": html, "representation": "storage"}}
        }
        r = requests.put(
            "https://3iai.atlassian.net/wiki/rest/api/content/" + existing_id,
            json=body, auth=(CONF_EMAIL, CONF_TOKEN))
        action = "업데이트"
    else:
        body = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "ancestors": [{"id": parent_id}],
            "body": {"storage": {"value": html, "representation": "storage"}}
        }
        r = requests.post(
            "https://3iai.atlassian.net/wiki/rest/api/content",
            json=body, auth=(CONF_EMAIL, CONF_TOKEN))
        action = "생성"

    if r.status_code not in (200, 201):
        print("      ERROR: 게시 실패 (" + str(r.status_code) + "): " + r.text[:300])
        return None
    print("      " + action + " 완료: " + title)
    return r.json().get("id")
