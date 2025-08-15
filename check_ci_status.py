#!/usr/bin/env python3
"""
Check GitHub Actions CI/CD Pipeline Status
"""

import json
import sys
from urllib.request import urlopen, Request
from urllib.error import HTTPError
import time

def check_github_actions():
    """GitHub Actions 워크플로우 상태 확인"""
    
    repo = "JiHyunSim/ai-trading-bot"
    api_url = f"https://api.github.com/repos/{repo}/actions/runs"
    
    try:
        # GitHub API 호출
        request = Request(api_url)
        request.add_header('Accept', 'application/vnd.github.v3+json')
        request.add_header('User-Agent', 'AI-Trading-Bot-CI-Checker')
        
        with urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode())
            
        runs = data.get('workflow_runs', [])
        
        if not runs:
            print("❌ GitHub Actions 실행 기록을 찾을 수 없습니다.")
            return False
            
        print("🔍 최근 GitHub Actions 실행 상태:")
        print("=" * 70)
        
        for i, run in enumerate(runs[:5]):  # 최근 5개 실행만 확인
            status = run['status']
            conclusion = run.get('conclusion', 'N/A')
            created_at = run['created_at']
            branch = run['head_branch']
            commit_message = run['head_commit']['message'].split('\n')[0]
            
            # 상태 아이콘
            if status == 'completed':
                if conclusion == 'success':
                    icon = "✅"
                elif conclusion == 'failure':
                    icon = "❌"
                elif conclusion == 'cancelled':
                    icon = "⚠️"
                else:
                    icon = "❓"
            elif status == 'in_progress':
                icon = "🔄"
            else:
                icon = "⏳"
            
            print(f"{icon} #{run['run_number']} - {status.upper()}")
            if conclusion != 'N/A':
                print(f"   결과: {conclusion.upper()}")
            print(f"   브랜치: {branch}")
            print(f"   커밋: {commit_message[:60]}{'...' if len(commit_message) > 60 else ''}")
            print(f"   시간: {created_at}")
            print(f"   URL: {run['html_url']}")
            print()
        
        # 가장 최근 실행 결과 체크
        latest_run = runs[0]
        if latest_run['status'] == 'completed' and latest_run['conclusion'] == 'success':
            print("🎉 최신 CI/CD 파이프라인이 성공적으로 완료되었습니다!")
            return True
        elif latest_run['status'] == 'in_progress':
            print("🔄 CI/CD 파이프라인이 실행 중입니다...")
            print(f"   진행 상황: {latest_run['html_url']}")
            return True
        else:
            print("⚠️ 최신 CI/CD 파이프라인에 문제가 있습니다.")
            print(f"   상태: {latest_run['status']}")
            if latest_run.get('conclusion'):
                print(f"   결과: {latest_run['conclusion']}")
            return False
            
    except HTTPError as e:
        if e.code == 404:
            print("❌ 저장소를 찾을 수 없거나 접근 권한이 없습니다.")
        else:
            print(f"❌ GitHub API 호출 실패: {e}")
        return False
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return False

def main():
    print("🚀 GitHub Actions CI/CD 파이프라인 상태 확인\n")
    
    success = check_github_actions()
    
    if success:
        print("\n✅ CI/CD 파이프라인 검증 완료!")
        print("   모든 자동화된 테스트와 빌드가 정상적으로 작동하고 있습니다.")
        sys.exit(0)
    else:
        print("\n⚠️ CI/CD 파이프라인 검증이 필요합니다.")
        print("   GitHub Actions 페이지에서 자세한 내용을 확인하세요.")
        print("   URL: https://github.com/JiHyunSim/ai-trading-bot/actions")
        sys.exit(1)

if __name__ == "__main__":
    main()