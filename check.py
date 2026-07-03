import csv

with open("glossary.csv", encoding="utf-8") as f:
    glossary = list(csv.DictReader(f))

with open("output_en.md", encoding="utf-8") as f:
    text = f.read()

print("=== 용어 발견 여부 ===")
found = []
for term in glossary:
    en = term["en"].strip()
    if en.lower() in text.lower():
        found.append(term)
        print("OK  " + en + " -> KO:" + term["ko"] + " / JA:" + term["ja"])
    else:
        print("--  " + en + " -> 이 페이지에 없음")

print("\n총 " + str(len(found)) + "/" + str(len(glossary)) + "개 용어 발견")

print("\n=== 혼용 표현 체크 ===")
checks = [
    ("Field Cam", "Field Camera"),
    ("Dollhouse View", "dollhouse view"),
    ("3D Workspace", "3d workspace"),
]
for a, b in checks:
    has_a = a in text
    has_b = b.lower() in text.lower()
    if has_a and has_b:
        print("WARN: " + a + " and " + b + " both found -> unify needed")
    elif has_b and not has_a:
        print("WARN: " + b + " found -> change to " + a)
    else:
        print("OK: " + a + " consistent")
