import requests

nm_id = 604298218

urls = [
    f"https://card.wb.ru/cards/v4/detail?appType=1&curr=rub&dest=-1257786&nm={nm_id}",
    f"https://card.wb.ru/cards/detail?appType=1&curr=rub&dest=-1257786&nm={nm_id}",
    f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx",
]

for url in urls:
    try:
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0.0.0 Safari/537.36",
                "Accept": "application/json,text/plain,*/*",
            },
            timeout=10,
        )

        print("\nURL:", url)
        print("STATUS:", r.status_code)
        print("FINAL:", r.url)
        print("LENGTH:", len(r.content))
        print("CONTENT-TYPE:", r.headers.get("content-type"))
        print("BODY:", r.text[:1000])

    except Exception as e:
        print("\nERROR:", url, repr(e))