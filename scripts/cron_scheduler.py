#!/usr/bin/env python3
"""
Cron Scheduler Setup for Data Maintenance
일일 데이터 유지보수 배치를 위한 크론탭 설정 도구
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path


def get_project_root():
    """프로젝트 루트 디렉토리 경로 반환"""
    return Path(__file__).parent.parent.absolute()


def get_python_path():
    """현재 Python 경로 반환"""
    return sys.executable


def create_cron_entry(schedule_time="0 10 * * *", symbols=None):
    """크론탭 엔트리 생성"""
    project_root = get_project_root()
    python_path = get_python_path()
    script_path = project_root / "scripts" / "daily_data_maintenance.py"
    log_path = project_root / "logs" / "daily_maintenance.log"
    
    # 로그 디렉토리 생성
    log_path.parent.mkdir(exist_ok=True)
    
    # 심볼 파라미터 추가
    symbol_args = f"--symbols {symbols}" if symbols else ""
    
    # 크론탭 엔트리 구성
    cron_entry = (
        f"{schedule_time} "
        f"cd {project_root} && "
        f"{python_path} {script_path} {symbol_args} "
        f">> {log_path} 2>&1"
    )
    
    return cron_entry


def get_current_crontab():
    """현재 크론탭 내용 조회"""
    try:
        result = subprocess.run(["crontab", "-l"], 
                              capture_output=True, text=True, check=True)
        return result.stdout.strip().split('\n') if result.stdout.strip() else []
    except subprocess.CalledProcessError:
        # 크론탭이 비어있는 경우
        return []


def install_cron_job(schedule_time="0 10 * * *", symbols=None, force=False):
    """크론 작업 설치"""
    cron_entry = create_cron_entry(schedule_time, symbols)
    current_crontab = get_current_crontab()
    
    # 기존 daily_data_maintenance 작업 확인
    maintenance_jobs = [line for line in current_crontab 
                       if "daily_data_maintenance.py" in line]
    
    if maintenance_jobs and not force:
        print("⚠️  Daily data maintenance cron job already exists:")
        for job in maintenance_jobs:
            print(f"   {job}")
        print("\nUse --force to replace existing job")
        return False
    
    # 기존 작업 제거 (force 모드)
    if force:
        current_crontab = [line for line in current_crontab 
                          if "daily_data_maintenance.py" not in line]
    
    # 새 작업 추가
    new_crontab = current_crontab + [cron_entry]
    
    # 크론탭 업데이트
    try:
        crontab_content = '\n'.join(new_crontab) + '\n'
        process = subprocess.Popen(["crontab", "-"], 
                                 stdin=subprocess.PIPE, text=True)
        process.communicate(input=crontab_content)
        
        if process.returncode == 0:
            print("✅ Daily data maintenance cron job installed successfully!")
            print(f"📅 Schedule: {schedule_time} (every day at 10:00 AM)")
            print(f"🔧 Command: {cron_entry}")
            return True
        else:
            print("❌ Failed to install cron job")
            return False
            
    except Exception as e:
        print(f"❌ Error installing cron job: {e}")
        return False


def remove_cron_job():
    """크론 작업 제거"""
    current_crontab = get_current_crontab()
    
    # daily_data_maintenance 관련 작업 찾기
    maintenance_jobs = [line for line in current_crontab 
                       if "daily_data_maintenance.py" in line]
    
    if not maintenance_jobs:
        print("ℹ️  No daily data maintenance cron jobs found")
        return True
    
    # 관련 작업 제거
    new_crontab = [line for line in current_crontab 
                  if "daily_data_maintenance.py" not in line]
    
    try:
        crontab_content = '\n'.join(new_crontab) + '\n' if new_crontab else ''
        process = subprocess.Popen(["crontab", "-"], 
                                 stdin=subprocess.PIPE, text=True)
        process.communicate(input=crontab_content)
        
        if process.returncode == 0:
            print(f"✅ Removed {len(maintenance_jobs)} daily data maintenance cron job(s)")
            return True
        else:
            print("❌ Failed to remove cron job")
            return False
            
    except Exception as e:
        print(f"❌ Error removing cron job: {e}")
        return False


def list_cron_jobs():
    """현재 크론 작업 목록 출력"""
    current_crontab = get_current_crontab()
    
    if not current_crontab:
        print("📭 No cron jobs found")
        return
    
    print("📋 Current cron jobs:")
    print("-" * 60)
    
    for i, job in enumerate(current_crontab, 1):
        if job.strip():
            is_maintenance = "daily_data_maintenance.py" in job
            marker = "🔧" if is_maintenance else "📌"
            print(f"{marker} {i}: {job}")
    
    print("-" * 60)
    
    # 데이터 유지보수 작업 강조
    maintenance_jobs = [line for line in current_crontab 
                       if "daily_data_maintenance.py" in line]
    
    if maintenance_jobs:
        print("\n🔧 Data Maintenance Jobs:")
        for job in maintenance_jobs:
            print(f"   {job}")


def validate_schedule(schedule):
    """크론 스케줄 형식 검증"""
    parts = schedule.split()
    if len(parts) != 5:
        return False, "Cron schedule must have 5 parts: minute hour day month weekday"
    
    # 기본적인 범위 검사
    ranges = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
    names = ["minute", "hour", "day", "month", "weekday"]
    
    for i, (part, (min_val, max_val), name) in enumerate(zip(parts, ranges, names)):
        if part == "*":
            continue
        
        try:
            # 단순한 숫자 체크
            if part.isdigit():
                val = int(part)
                if not (min_val <= val <= max_val):
                    return False, f"{name} value {val} out of range ({min_val}-{max_val})"
            # 더 복잡한 형식은 일단 통과
        except ValueError:
            # 복잡한 cron 표현식은 검증하지 않음
            continue
    
    return True, "Valid schedule"


def create_systemd_service():
    """Systemd 서비스 파일 생성"""
    project_root = get_project_root()
    python_path = get_python_path()
    script_path = project_root / "scripts" / "daily_data_maintenance.py"
    
    service_content = f"""[Unit]
Description=AI Trading Bot - Daily Data Maintenance
After=network.target postgresql.service

[Service]
Type=oneshot
User={os.getenv('USER', 'ubuntu')}
WorkingDirectory={project_root}
ExecStart={python_path} {script_path}
Environment=PATH={os.environ.get('PATH', '')}
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
    
    timer_content = """[Unit]
Description=Run Daily Data Maintenance at 10:00 AM
Requires=ai-trading-bot-maintenance.service

[Timer]
OnCalendar=*-*-* 10:00:00
Persistent=true

[Install]
WantedBy=timers.target
"""
    
    # 서비스 파일 저장
    systemd_dir = project_root / "scripts" / "systemd"
    systemd_dir.mkdir(exist_ok=True)
    
    service_file = systemd_dir / "ai-trading-bot-maintenance.service"
    timer_file = systemd_dir / "ai-trading-bot-maintenance.timer"
    
    with open(service_file, 'w') as f:
        f.write(service_content)
    
    with open(timer_file, 'w') as f:
        f.write(timer_content)
    
    print(f"✅ Systemd service files created:")
    print(f"   📝 {service_file}")
    print(f"   📝 {timer_file}")
    print(f"\n🔧 To install systemd service:")
    print(f"   sudo cp {service_file} /etc/systemd/system/")
    print(f"   sudo cp {timer_file} /etc/systemd/system/")
    print(f"   sudo systemctl daemon-reload")
    print(f"   sudo systemctl enable ai-trading-bot-maintenance.timer")
    print(f"   sudo systemctl start ai-trading-bot-maintenance.timer")


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="Cron Scheduler for Daily Data Maintenance")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # install 명령
    install_parser = subparsers.add_parser("install", help="Install cron job")
    install_parser.add_argument("--schedule", default="0 10 * * *", 
                               help="Cron schedule (default: 0 10 * * * - daily at 10:00 AM)")
    install_parser.add_argument("--symbols", help="Comma-separated symbols to process")
    install_parser.add_argument("--force", action="store_true", 
                               help="Replace existing cron job")
    
    # remove 명령
    subparsers.add_parser("remove", help="Remove cron job")
    
    # list 명령  
    subparsers.add_parser("list", help="List current cron jobs")
    
    # systemd 명령
    subparsers.add_parser("systemd", help="Create systemd service files")
    
    # test 명령
    test_parser = subparsers.add_parser("test", help="Test cron schedule format")
    test_parser.add_argument("schedule", help="Cron schedule to test")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == "install":
        # 스케줄 검증
        is_valid, message = validate_schedule(args.schedule)
        if not is_valid:
            print(f"❌ Invalid schedule: {message}")
            sys.exit(1)
        
        print(f"📅 Installing daily data maintenance cron job...")
        print(f"   Schedule: {args.schedule}")
        if args.symbols:
            print(f"   Symbols: {args.symbols}")
        
        success = install_cron_job(args.schedule, args.symbols, args.force)
        sys.exit(0 if success else 1)
    
    elif args.command == "remove":
        print("🗑️  Removing daily data maintenance cron job...")
        success = remove_cron_job()
        sys.exit(0 if success else 1)
    
    elif args.command == "list":
        list_cron_jobs()
    
    elif args.command == "systemd":
        print("🔧 Creating systemd service files...")
        create_systemd_service()
    
    elif args.command == "test":
        is_valid, message = validate_schedule(args.schedule)
        if is_valid:
            print(f"✅ Schedule '{args.schedule}' is valid")
            
            # 스케줄 설명
            parts = args.schedule.split()
            print(f"   Minute: {parts[0]}")
            print(f"   Hour: {parts[1]}")
            print(f"   Day: {parts[2]}")
            print(f"   Month: {parts[3]}")
            print(f"   Weekday: {parts[4]}")
        else:
            print(f"❌ Schedule '{args.schedule}' is invalid: {message}")
            sys.exit(1)


if __name__ == "__main__":
    main()