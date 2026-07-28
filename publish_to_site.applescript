try
	set theURL to text returned of (display dialog "웹사이트에 반영할 Confluence 페이지 URL을 입력하세요:" default answer "" with title "Beamo 매뉴얼 → 웹사이트 반영")
on error number -128
	return
end try

if theURL is "" then
	display dialog "URL이 비어있습니다." with title "오류" buttons {"확인"} default button "확인"
	return
end if

set projectPath to "/Users/3i-a1-2021-300/Desktop/AX/Beano User Maual _ ENG:KR:JP"
set pythonPath to "/usr/bin/python3"
set theCommand to "cd " & quoted form of projectPath & " && " & quoted form of pythonPath & " publish_to_site.py " & quoted form of theURL

tell application "Terminal"
	activate
	do script theCommand
end tell
