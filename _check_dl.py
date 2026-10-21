import urllib.request, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

url = 'https://www.capital.com.tw/apiforum/downloads'
req = urllib.request.urlopen(url, timeout=15)
content = req.read().decode('utf-8', errors='ignore')

# Find all URLs that look like downloads
pattern = r'https?://[^\s"<>]+?\.(?:zip|exe|msi|rar|7z)'
dl_links = re.findall(pattern, content)
if dl_links:
    print("Download links found:")
    for d in set(dl_links):
        print(f"  {d}")
else:
    print("No direct download links in HTML (SPA page)")
    # Look for API endpoints
    api_pattern = r'/api/[^\s"<>]+'
    apis = re.findall(api_pattern, content)
    for a in set(apis):
        print(f"  API: {a}")

# Also check for the test program download
test_url = 'https://www.capital.com.tw/campaign/stock/API/index.html'
req2 = urllib.request.urlopen(test_url, timeout=15)
content2 = req2.read().decode('utf-8', errors='ignore')
dl2 = re.findall(pattern, content2)
if dl2:
    print("\nFrom main API page:")
    for d in set(dl2):
        print(f"  {d}")
