<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:py="http://purl.org/kid/ns#"
    py:extends="'master.kid'">
<head>
<meta content="text/html; charset=utf-8" http-equiv="Content-Type" py:replace="''"/>
<title>$title</title>
</head>
<body>
<h2>$title</h2>
<span py:if="search_bar">${search_bar.display(method='GET', action=action, value=searchvalue, options=options)}</span>


${grid.display(list)}
<a href="${tg.url('./new')}">Add ( + )</a>
</body>
</html>
