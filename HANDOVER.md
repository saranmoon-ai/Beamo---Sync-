# Beamo 매뉴얼 시스템 — 인수인계 문서

> 이 문서는 Beamo 매뉴얼 사이트의 콘텐츠 관리 시스템 전체를 처음 보는 사람도 이해할 수 있도록 정리한 문서입니다. 기획 의도, 전체 구조, 각 부분의 기능과 사용법, 주의사항을 담았습니다.

---

## 1. 기획 의도 — 왜 이렇게 만들었나

### 원래 있던 것
Beamo 매뉴얼은 컨플루언스에 문서를 쓰면, 자동으로 3개 언어(한/영/일)로 번역되고 웹사이트에 반영되는 자동화 파이프라인이 이미 있었습니다. 신규 문서를 추가할 때는 이 흐름이 잘 작동했습니다.

### 문제
이미 배포된 문서에서 오타 하나, 링크 하나만 고치고 싶어도:

- 컨플루언스 → 번역 → 발행이라는 전체 과정을 다시 타거나
- 개발 지식이 있는 사람이 사이트 코드 파일(`content-data.js`)을 직접 열어 고쳐야 했습니다.

비개발자가 간단한 수정조차 할 수 없는 구조였습니다.

### 해결
**두 갈래 경로를 하나의 저장소로 합치는 구조**를 만들었습니다.

- **신규 문서**: 기존처럼 컨플루언스 → 자동 번역 파이프라인 (그대로 유지, 폐기 아님)
- **기존 문서 수정**: 브라우저에서 깃허브 로그인만 하면 바로 고칠 수 있는 편집기(`/admin`) 신규 추가

두 경로 모두 결과적으로 같은 파일들(`content/articles/*.json`)을 갱신하고, 자동 빌드 장치가 사이트에 반영합니다.

---

## 2. 전체 그림

```
[신규 문서]                         [기존 문서 수정]
컨플루언스 작성                      /admin 접속 → 깃허브 로그인
   ↓                                    ↓
자동 번역 (한/영/일)                  문서 선택 → 내용 수정
   ↓                                    ↓
publish_to_site.py                  Decap CMS 저장
   ↓                                    ↓
        content/articles/<문서key>.json  ← 두 경로가 만나는 지점
                    ↓
        GitHub Actions 자동 빌드 (build-content.yml)
                    ↓
             content-data.js 재생성
                    ↓
              라이브 사이트 반영
```

이 구조에서 가장 중요한 원칙: **`content/articles/<key>.json`이 진짜 원본(source of truth)이고, `content-data.js`는 그걸로부터 자동 생성되는 산출물**입니다. `content-data.js`를 사람이 직접 고치면 다음 자동 빌드 때 덮어써져 사라집니다.

---

## 3. 번역 자동화 파이프라인 (신규 문서용, 기존 기능)

### 위치
`/Users/3i-a1-2021-300/Desktop/AX/Beano User Maual _ ENG:KR:JP/`

### 사용법
```bash
python3 publish_to_site.py <컨플루언스 페이지 URL>
```

### 동작 순서
1. 컨플루언스 URL에서 페이지 ID 추출
2. 컨플루언스 원본(제목+본문+첨부파일) 가져오기, 원본 언어 자동 감지
3. 용어집(`glossary.csv`)과 대조해서 용어 통일
4. 이 컨플루언스 페이지가 사이트의 어떤 문서(`key`)에 해당하는지 확인 — 처음 보는 문서면 팝업 창(Tkinter)이 떠서 버전·플랫폼·대상 사용자·스텝(챕터) 번호를 직접 입력해야 함
5. 나머지 2개 언어로 번역 (Anthropic API 사용), 필요하면 컨플루언스에도 번역본을 재게시
6. `content/articles/<key>.json` 갱신 + 로컬 git 커밋 (⚠️ push는 자동으로 안 함 — 직접 push 필요)

완료되면 macOS 알림 팝업으로 결과 요약(문서 key, 번역된 언어, 용어 통일 내역, 커밋 여부)을 보여주고, 사이트 미리보기(`index.html`)를 브라우저로 엽니다.

### 파일별 역할

| 파일 | 역할 |
|---|---|
| `publish_to_site.py` | 메인 실행 스크립트. 위 6단계를 순서대로 수행 |
| `sync.py` | 컨플루언스 API 인증 정보, 페이지 가져오기, 용어집 관련 공용 함수 |
| `publish_confluence.py` | 매크로 보호/복원, 번역 API 호출, 컨플루언스 하위 페이지 검색 등 공용 함수 |
| `check.py` | 보조 점검 스크립트 |
| `page_map.json` | 컨플루언스 페이지 ID ↔ 사이트 문서 key 매핑 테이블 |
| `glossary.csv` | 번역 시 용어 통일에 쓰이는 용어집 |

### 필요 환경변수 (`~/.zshrc`에 설정되어 있어야 함)
- `CONF_EMAIL`, `CONF_TOKEN` — 컨플루언스 API 인증
- `ANTHROPIC_API_KEY` — 번역 API 호출용

### 주의사항
- **`SITE_DIR` 환경변수로 오버라이드 가능** (`publish_to_site.py` 상단). 기본값은 `/Users/3i-a1-2021-300/Desktop/Beamo manual website`. 로컬에서 사이트 폴더를 옮기거나 이름을 바꾸면 `SITE_DIR` 환경변수를 설정하거나 기본값을 고쳐야 함 (예전에 폴더명이 바뀌면서 한 번 끊어졌던 적 있음). GitHub Actions에서는 워크플로가 `SITE_DIR`을 자동으로 설정해줌.
- 이 스크립트는 이제 `content-data.js`를 직접 건드리지 않고, `content/articles/<key>.json` 개별 파일만 읽고 씀 (편집기 쪽과 같은 소스를 공유하도록 리팩터됨).
- **로컬(Mac Automator 버튼)에서는** git commit까지는 자동이지만 **push는 사용자가 직접** 해야 함.
- **GitHub Actions에서 실행할 때는** 새 브랜치를 만들어 커밋 + push + PR 생성까지 자동으로 함 (아래 3-1절 참고). `CI_MODE`는 `GITHUB_ACTIONS` 환경변수로 자동 감지되며, 이 값에 따라 팝업창(Tkinter/osascript) 대신 콘솔 출력 + PR로 동작이 바뀜.

---

## 3-1. 팀원 누구나 쓸 수 있는 GitHub Actions 실행 경로 (신규 추가)

Automator 버튼은 이 컴퓨터(사장님 Mac)에서만 동작합니다. 팀원들도 신규 문서 번역을 실행할 수 있도록, 같은 파이썬 파이프라인을 **GitHub Actions**로도 실행할 수 있게 만들었습니다. Claude Code나 별도 앱 설치 없이 **브라우저 + 깃허브 로그인**만 있으면 됩니다.

### 사용법 (팀원 기준)
1. 저장소 `saranmoon-ai/Beamo-manual-3.0` → **Actions** 탭 → **"Translate & Register New Manual Doc"** 워크플로 선택
2. **Run workflow** 버튼 클릭
3. 컨플루언스 URL 입력 (신규 문서라면 카테고리/버전/플랫폼/대상 사용자/스텝 번호도 같이 입력 — 기존 문서 업데이트면 URL만 입력해도 됨)
4. 실행 완료 후 같은 저장소에 자동으로 생성된 **Pull Request**를 열어서 내용 확인 → 문제 없으면 본인이 직접 Merge

### 사전 준비 (딱 한 번만, 관리자가 해야 함)
1. **팀원을 두 저장소에 초대**: `saranmoon-ai/Beamo-manual-3.0` (쓰기 권한), `saranmoon-ai/Beamo---Sync-` (읽기 권한이면 충분 — PAT로 접근하므로)
2. **`Beamo-manual-3.0` 저장소에 Secrets 등록** (Settings → Secrets and variables → Actions):

   | Secret 이름 | 값 |
   |---|---|
   | `CONF_EMAIL` | 컨플루언스 API용 이메일 (지금 `~/.zshrc`에 있는 것과 동일한 값) |
   | `CONF_TOKEN` | 컨플루언스 API 토큰 |
   | `ANTHROPIC_API_KEY` | 번역용 Anthropic API 키 |
   | `SYNC_REPO_TOKEN` | `Beamo---Sync-` 저장소를 체크아웃 + push할 수 있는 GitHub Personal Access Token (fine-grained PAT, 해당 저장소 Contents: Read and write 권한) |

   (`GITHUB_TOKEN`은 GitHub가 실행마다 자동으로 만들어주므로 따로 등록할 필요 없음 — `Beamo-manual-3.0` 저장소 자체에 대한 커밋/PR 생성에 쓰임.)

### 동작 방식
- 워크플로 파일: `Beamo-manual-3.0` 저장소의 `.github/workflows/translate-new-doc.yml`
- `Beamo-manual-3.0`(사이트)과 `Beamo---Sync-`(스크립트+용어집+매핑)를 각각 체크아웃해서 최신 상태로 실행 — 용어집(`glossary.csv`)이나 매핑(`page_map.json`)을 업데이트해도 워크플로를 다시 배포할 필요 없이 바로 반영됨.
- 신규 문서 매핑(`page_map.json`)이 새로 생기면 `Beamo---Sync-` 저장소의 main 브랜치에 바로 커밋 (충돌 위험이 낮은 부수 데이터라 PR 없이 직접 반영).
- 웹사이트 콘텐츠(`content/articles/<key>.json`, 이미지)는 새 브랜치 + PR로 반영 (사람이 검토 후 병합).
- 로컬 Automator 버튼과 완전히 같은 파이썬 코드(`publish_to_site.py`)를 쓰므로, 로직을 고치면 두 경로 모두에 자동으로 적용됨 (별도로 두 벌 관리할 필요 없음).

---

## 4. 매뉴얼 웹사이트 (정적 사이트)

### 위치 / 주소
- 로컬: `/Users/3i-a1-2021-300/Desktop/Beamo manual website`
- 저장소: `saranmoon-ai/Beamo-manual-3.0` (GitHub Pages)
- 라이브 주소: `https://saranmoon-ai.github.io/Beamo-manual-3.0/`

### 구조
순수 정적 HTML/CSS/JS 사이트입니다. Node.js나 별도 빌드 도구 없이, 브라우저가 파일을 그대로 읽습니다.

| 파일/폴더 | 역할 |
|---|---|
| `index.html` | 메인 페이지, 스크립트 로드 순서 관리 |
| `app.js` | 화면 렌더링, 검색·필터링, 문서 간 이동 로직 |
| `i18n-ui.js` | 화면에 쓰이는 UI 텍스트(버튼 이름 등)의 3개 언어 번역 |
| `style.css` | 디자인 |
| `content-data.js` | **빌드 산출물** — 아래 `content/articles/*.json`을 자동으로 합쳐서 만들어짐. **직접 수정 금지** |
| `content/articles/*.json` | **진짜 원본** — 문서 하나당 파일 하나 (현재 32개) |
| `content/_order-manifest.json` | 문서 32개의 원래 순서를 기록해둔 파일. `order` 값이 같은 문서가 여러 개 있어서, 화면에 뜨는 순서를 정확히 재현하려고 만듦. 편집기가 다루는 대상이 아님 |
| `scripts/split_content.py` | `content-data.js` → `content/articles/*.json` 분리 스크립트 (1회성, 이미 실행 완료) |
| `scripts/build_content.py` | `content/articles/*.json` → `content-data.js` 재생성 스크립트 (상시 사용) |
| `.github/workflows/build-content.yml` | `content/articles/**`가 바뀌어 push되면 자동으로 `build_content.py`를 실행하고, 바뀐 `content-data.js`를 `github-actions[bot]` 이름으로 커밋 |

### 자동 빌드 흐름 이해하기
1. 편집기(또는 컨플루언스 파이프라인)가 `content/articles/문서.json` 하나를 고쳐서 push
2. GitHub Actions가 트리거됨 (`content/articles/**` 경로 변경 감지)
3. `content/articles/` 안의 문서 파일 전부를 다시 읽어서 `content-data.js`를 처음부터 재생성
4. 결과가 이전과 다르면 `content-data.js`만 `github-actions[bot]` 이름으로 자동 커밋

**즉, 커밋 기록에 `github-actions[bot]`이 보이는 건 정상이고, 걱정할 필요 없는 자동화입니다.**

### 주의사항
- `content-data.js`를 직접 고치면 다음 자동 빌드 때 사라짐. 항상 `content/articles/<key>.json`을 고칠 것.
- GitHub Pages는 "Deploy from branch(main)" 방식(Actions 기반 배포 아님) — 이 워크플로우는 그 설정을 그대로 유지하면서 빌드만 추가한 것.

---

## 5. 편집기 (`/admin`, Decap CMS)

### 주소
`https://saranmoon-ai.github.io/Beamo-manual-3.0/admin/`

같은 사이트 안의 페이지 하나일 뿐, 별도로 호스팅되는 게 아닙니다 (레포 안 `admin/` 폴더 하나 추가한 것).

### 권한 구조 (중요)
- `/admin` 페이지 자체는 **누구나 접속 가능**합니다 (공개 URL). 로그인 화면만 보임.
- 실제로 문서를 저장하려면 **깃허브 계정으로 로그인 + 그 계정이 저장소(`Beamo-manual-3.0`) 협업자 권한**을 가지고 있어야 합니다.
- 즉 방어선은 "URL을 숨기는 것"이 아니라 "깃허브 저장소 협업자 목록"입니다. 권한 없는 사람이 로그인해도 저장 시 깃허브가 거부합니다.
- 이 레포가 public이든 private이든 이 권한 구조는 동일합니다.

### 기능
- **문서 목록** (왼쪽): 문서 32개를 검색해서 찾을 수 있음
- **문서 편집** (오른쪽): 클릭한 문서의 메타데이터(버전/플랫폼/대상 사용자/스텝/정렬순서) + 한국어·영어·일본어 각각 제목+본문
- **본문 편집기**: 커스텀으로 만든 "화면에 보이는 그대로 편집" 방식 (실제 렌더링된 제목·문단·목록이 보이고, 그 위를 클릭해서 바로 타이핑하면 수정됨). 마크다운으로 변환하지 않고 **원본 HTML을 그대로 유지**해서 저장 — 컨플루언스에서 넘어온 복잡한 표·인용구 서식이 깨질 위험을 없앤 방식.
  - 🖼 **이미지 삽입**: 미디어 라이브러리에서 사진 선택/업로드 → 커서 위치에 삽입
  - 🔗 **링크 삽입**: 외부 URL로 연결되는 링크
  - 📄 **문서 링크**: 사이트 안의 다른 문서로 이동하는 링크 (이동할 문서의 `key`를 직접 입력)
- **저장**: 저장 버튼 누르면 → 깃허브에 커밋 → GitHub Actions 자동 빌드 → 라이브 사이트 반영까지 전부 자동으로 이어짐

### 인증 구조 (기술적 배경)
- **GitHub OAuth App** 등록되어 있음 (Homepage: 매뉴얼 사이트 주소, Callback: 아래 워커 주소 + `/callback`)
- **Cloudflare Workers 프록시** (워커 이름: `beamo-cms-oauth`, Cloudflare 계정: `saran-moon`) — 깃허브 로그인 토큰 교환을 처리하는 작은 서버. 사이트와는 별개로 Cloudflare에 배포되어 있음.
  - 코드 위치: `admin/oauth-worker/index.js` (배포는 Cloudflare 대시보드에서 코드를 붙여넣는 방식으로 함, Node.js/wrangler CLI 안 씀 — 이 컴퓨터에 Node.js가 없어서)
  - Client ID/Secret은 Cloudflare 워커의 "Variables and secrets"에 등록되어 있음. **재발급하면 여기도 다시 등록해야 함.**

### 로그인 화면 브랜딩
로그인 화면의 로고와 버튼 색상을 beamo 브랜드로 바꿔뒀습니다 (`admin/index.html` 안 CSS). 이건 Decap CMS가 공식 지원하는 기능이 아니라, 화면에 보이는 클래스 이름을 직접 타겟팅한 방식이라 **Decap 버전이 크게 업데이트되면 깨질 수 있음** (안전하게 실패함 — 스타일만 안 먹히고 기능은 정상 동작).

### 주의사항 (꼭 읽어야 하는 부분)

1. **언어 간 자동 동기화 안 됨** — 영어만 고치고 저장하면 한국어·일본어는 그대로 남습니다. 자동 번역 기능이 없어서, 세 언어를 다 고쳐야 하면 직접 하나씩 확인하고 수정해야 합니다. (다국어 콘텐츠 섹션 위에 이 사실을 알리는 안내 문구를 넣어뒀습니다.)
2. **이미지는 한 번에 한 장씩만 삽입 가능** — Decap CMS 자체의 제한. 여러 장을 한꺼번에 준비해두고 싶으면, github.com에서 저장소의 `images/` 폴더에 직접 여러 파일을 드래그해서 올려두고, 편집기에서는 그중 필요한 것만 골라 삽입하는 방식을 추천.
3. **"+ 새 문서" 버튼은 아예 없앰** — 신규 문서는 컨플루언스 → 번역 자동화 경로로만 만들 수 있도록(그쪽에만 자동 번역, 분류 정보 입력 팝업 등이 있음), 편집기 설정(`admin/config.yml`의 `create: false`)에서 새 문서 생성 버튼 자체를 제거했습니다. 편집기는 **기존 문서 수정 전용**입니다.
4. **`key` 필드는 저장 후 절대 바꾸지 말 것** — 파일명, 이미지 폴더, 컨플루언스 매핑(`page_map.json`)이 전부 이 값과 연결되어 있습니다. 바꾸면 새 파일이 생겨버리고 기존 파일과 연결이 끊깁니다.
5. **문서 링크 삽입 시 오타 주의** — 이동할 문서의 `key`를 직접 입력하는 방식이라, 틀리게 입력해도 별도 경고 없이 그냥 깨진 링크가 됩니다. 왼쪽 문서 목록에 보이는 이름을 그대로 참고할 것.
6. **로컬 미리보기 불가** — 이 편집기는 실제 배포된 사이트에서만 테스트할 수 있습니다 (로컬 파일로 열면 정상 동작 안 함).

---

## 6. 전체 파일 위치 요약

| 구분 | 경로 |
|---|---|
| 매뉴얼 사이트 (로컬) | `/Users/3i-a1-2021-300/Desktop/Beamo manual website` |
| 매뉴얼 사이트 (저장소) | `saranmoon-ai/Beamo-manual-3.0` |
| 매뉴얼 사이트 (라이브) | `https://saranmoon-ai.github.io/Beamo-manual-3.0/` |
| 편집기 | `https://saranmoon-ai.github.io/Beamo-manual-3.0/admin/` |
| 번역 자동화 파이프라인 | `/Users/3i-a1-2021-300/Desktop/AX/Beano User Maual _ ENG:KR:JP/` |
| 팀원용 GitHub Actions 워크플로 | `Beamo-manual-3.0` 저장소의 `.github/workflows/translate-new-doc.yml` |
| OAuth 프록시 (Cloudflare Workers) | `beamo-cms-oauth.saran-moon.workers.dev` |

## 7. 필요 계정 / 환경변수 정리

| 항목 | 용도 | 위치 |
|---|---|---|
| `CONF_EMAIL`, `CONF_TOKEN` | 컨플루언스 API 인증 | `~/.zshrc` (로컬) + `Beamo-manual-3.0` 저장소 Secrets (팀원용 Actions) |
| `ANTHROPIC_API_KEY` | 번역 API | `~/.zshrc` (로컬) + `Beamo-manual-3.0` 저장소 Secrets (팀원용 Actions) |
| `SYNC_REPO_TOKEN` | Actions에서 `Beamo---Sync-` 저장소 체크아웃/push용 PAT | `Beamo-manual-3.0` 저장소 Secrets |
| GitHub OAuth App (Client ID/Secret) | 편집기 로그인 | Cloudflare 워커의 Secret |
| Cloudflare 계정 | OAuth 프록시 호스팅 | `saran-moon` |
| GitHub 저장소 협업자 권한 | 실제 편집 권한의 핵심 | 저장소 Settings → Collaborators |

---

*최초 작성: 2026-07-24 (콘텐츠 구조 분리 + 편집기 도입 작업 완료 시점)*

---

## 8. 알려진 이슈 / 수정 이력

**2026-08-26 — 같은 문서를 재실행하면 파이프라인이 죽던 버그 (수정 완료)**

`git_commit_site_ci`의 브랜치명이 `translate/<key>-<page_id>`로 문서마다 고정되어 있어서, 이전 실행이 만든 원격 브랜치가 아직 남아있으면(예: 이전 실행이 push 이후 단계에서 실패했거나, PR이 머지/종료된 뒤에도 브랜치가 삭제되지 않은 경우) 매번 새로 만든 로컬 브랜치와 히스토리가 갈라져 있어 push가 non-fast-forward로 거부되고 그대로 스크립트가 죽는 문제가 있었습니다.

수정 내용: push가 실패하면 (1) 같은 브랜치로 이미 열린 PR이 있는지 확인해서 있으면 그 PR을 재사용하고, (2) 열린 PR이 없는 버려진 브랜치면 원격 브랜치를 정리하고 한 번 더 push를 시도하도록 `publish_to_site.py`의 `git_commit_site_ci`를 수정했습니다. 커밋: `2af1431` (`saranmoon-ai/Beamo---Sync-`).

**2026-08-26 — PR 자동 생성이 실패하는 문제 (저장소 설정 문제, 코드 버그 아님)**

위 수정을 실제로 테스트하던 중, `gh pr create`가 `GitHub Actions is not permitted to create or approve pull requests`로 실패하는 걸 발견했습니다. 원인은 `Beamo-manual-3.0` 저장소의 **Settings → Actions → General → Workflow permissions → "Allow GitHub Actions to create and approve pull requests"** 체크박스가 꺼져 있었기 때문입니다. 스크립트 코드와는 무관한, 저장소 자체의 보안 설정입니다.

⚠️ **이 설정은 저장소를 새로 만들거나(fork, transfer, 재생성 등) 기본값으로 되돌리면 다시 꺼진 상태로 시작됩니다.** 껐다 켜는 건 코드로 안 되고(워크플로가 스스로에게 권한을 더 줄 수는 없음, GitHub의 의도된 보안 제약), 저장소 관리자 권한이 있는 사람이 한 번 켜줘야 합니다. UI로 켜는 방법은 위 경로 그대로 체크박스 클릭 후 저장이고, 명령줄로 한 번에 켜고 싶다면 저장소 관리자 권한이 있는 계정으로 다음을 실행하면 됩니다:

```
gh api --method PUT repos/saranmoon-ai/Beamo-manual-3.0/actions/permissions/workflow \
  -f default_workflow_permissions=write \
  -F can_approve_pull_request_reviews=true
```

---

## 9. 저장소를 다른 사람에게 넘길 때 체크리스트

이 시스템은 여러 개인 계정(깃허브 개인 PAT, 컨플루언스 개인 계정, Cloudflare 개인 계정 등)에 묶여 있는 부분이 많습니다. 담당자가 바뀌거나 저장소 소유권이 이전될 때, 아래 항목을 확인하지 않으면 **아무 에러 메시지 없이 조용히 멈추는 부분이 많으니** 순서대로 확인해주세요.

- [ ] **저장소 접근 권한**: 새 담당자를 `saranmoon-ai/Beamo-manual-3.0`(쓰기 권한 필요)과 `saranmoon-ai/Beamo---Sync-`(최소 읽기 권한)에 Collaborator로 추가
- [ ] **컨플루언스 API 인증** (`CONF_EMAIL`, `CONF_TOKEN`): 기존 발급자의 컨플루언스 계정이 비활성화되면 번역 파이프라인이 조용히 실패합니다. 새 계정 기준으로 토큰을 재발급하고 `~/.zshrc`(로컬)와 `Beamo-manual-3.0` 저장소 Secrets(팀원용 Actions) 둘 다 갱신
- [ ] **번역 API 키** (`ANTHROPIC_API_KEY`): 개인 키인지 조직 소유 키인지 확인. 개인 키라면 조직 소유 키로 교체 권장
- [ ] **`SYNC_REPO_TOKEN`** (Actions가 `Beamo---Sync-` 저장소를 체크아웃/push하는 데 쓰는 fine-grained PAT): 발급자 계정이 비활성화되거나 PAT 만료일이 지나면 CI가 전부 실패합니다. 새 계정으로 재발급 후 `Beamo-manual-3.0` 저장소 Secrets에 갱신
- [ ] **GitHub OAuth App** (편집기 `/admin` 로그인용): 소유권/Client Secret 확인 (Settings → Developer settings → OAuth Apps). 재발급하면 Cloudflare 워커의 "Variables and secrets"에도 반드시 다시 등록
- [ ] **Cloudflare 계정** (`saran-moon`, OAuth 프록시 워커 `beamo-cms-oauth` 호스팅): 새 담당자를 팀 멤버로 초대하거나 계정 자체를 이전
- [ ] **"Allow GitHub Actions to create and approve pull requests" 저장소 설정** (2026-08-26 기준 `Beamo-manual-3.0`에서는 켜져 있음, 확인 완료): 새 담당자에게 넘기거나 저장소를 새로 만들었다면(fork, transfer, 재생성 등) 이 설정이 꺼진 상태로 리셋되니 반드시 다시 확인할 것.
  - 확인/설정 위치: `Beamo-manual-3.0` 저장소 → **Settings → Actions → General → Workflow permissions** → "Allow GitHub Actions to create and approve pull requests" 체크박스 확인 후 **Save** (URL: `https://github.com/saranmoon-ai/Beamo-manual-3.0/settings/actions`)
  - 또는 관리자 권한 계정으로 명령줄에서 한 번에:
    ```
    gh api --method PUT repos/saranmoon-ai/Beamo-manual-3.0/actions/permissions/workflow -f default_workflow_permissions=write -F can_approve_pull_request_reviews=true
    ```
  - 자세한 배경(왜 필요한지)은 위 8번 항목 참고
- [ ] **위 시크릿 4종(`CONF_EMAIL`/`CONF_TOKEN`/`ANTHROPIC_API_KEY`/`SYNC_REPO_TOKEN`)이 `Beamo-manual-3.0` 저장소 Settings → Secrets and variables → Actions에 실제로 등록돼 있는지 재확인** — 저장소를 새로 만들거나 fork한 경우 Secrets는 자동으로 복사되지 않습니다
- [ ] **용어집(`glossary.csv`) 관리 프로세스 인수인계**: 이 파일을 누가, 어떤 방식으로 최신 상태로 유지하는지 확인 (담당자마다 다를 수 있는 부분이라 별도 확인 필요) 또한 새롭게 업데이트가 필요한 경우 클로드 요청하거나 CSV 파일 새로 업데이트할 것. 
