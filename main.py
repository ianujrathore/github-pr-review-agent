import httpx
import os
import re
import sys
import asyncio
from dotenv import load_dotenv
from groq import AsyncGroq

load_dotenv()

groq_client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

def extract_pr_info(pr_url: str):
    pattern = r"github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    match = re.search(pattern, pr_url)
    if not match:
        print("❌ Invalid GitHub PR URL")
        sys.exit(1)
    return match.group(1), match.group(2), match.group(3)

async def fetch_pr_diff(owner: str, repo: str, pr_number: str):
    token = os.getenv("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github.v3.diff",
        "User-Agent": "PR-Review-Agent",
        "Authorization": f"Bearer {token}"
    }
    
    diff_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}.diff"
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(diff_url, headers=headers)
        
        if response.status_code != 200:
            print(f"❌ GitHub error: {response.status_code}")
            sys.exit(1)
        
        diff_text = response.text
        
        # Get PR title
        info_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        info_headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "PR-Review-Agent",
            "Authorization": f"Bearer {token}"
        }
        info_response = await client.get(info_url, headers=info_headers)
        
        if info_response.status_code == 200:
            info = info_response.json()
            title = info.get("title", "Unknown")
            author = info.get("user", {}).get("login", "Unknown")
            files = info.get("changed_files", 0)
        else:
            title = f"{repo}#{pr_number}"
            author = "Unknown"
            files = 0
        
        return {
            "title": title,
            "author": author,
            "files": files,
            "diff": diff_text[:8000]
        }

async def stream_review(pr_data: dict):
    prompt = f"""Review this PR code diff:

PR: {pr_data['title']}
Author: {pr_data['author']}

Diff:
{pr_data['diff']}

Provide a structured review:

🐛 BUGS FOUND:
(List any bugs, logic errors, edge cases. Or "None found")

🔒 SECURITY ISSUES:
(List any vulnerabilities. Or "None found")

💡 IMPROVEMENTS:
(Code quality, performance, readability suggestions)

✅ GOOD PRACTICES:
(What's done well)"""

    print("\n" + "="*60)
    print(f"📋 PR: {pr_data['title']}")
    print(f"👤 Author: {pr_data['author']}")
    print(f"📁 Files Changed: {pr_data['files']}")
    print("="*60)
    print("\n⏳ Analyzing code...\n")
    
    stream = await groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        temperature=0.3,
    )
    
    async for chunk in stream:
        content = chunk.choices[0].delta.content
        if content:
            print(content, end="", flush=True)
    
    print("\n\n✅ Review Complete!\n")

async def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <github-pr-url>")
        print("Example: python main.py https://github.com/facebook/react/pull/27522")
        sys.exit(1)
    
    pr_url = sys.argv[1]
    owner, repo, pr_number = extract_pr_info(pr_url)
    
    print(f"\n🔍 Fetching PR diff from {owner}/{repo}...")
    pr_data = await fetch_pr_diff(owner, repo, pr_number)
    
    await stream_review(pr_data)

if __name__ == "__main__":
    asyncio.run(main())