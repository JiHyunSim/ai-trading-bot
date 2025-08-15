#!/usr/bin/env python3
"""
AI Trading Bot - 누락 데이터 감지 및 보완 스크립트
"""

import asyncio
import sys
import argparse
from datetime import datetime, timedelta
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'services', 'collector'))

from app.data.gap_detector import DataGapDetector
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

async def main():
    parser = argparse.ArgumentParser(description='AI Trading Bot Gap Filling Tool')
    parser.add_argument('--symbol', default='BTC-USDT-SWAP', help='Trading symbol')
    parser.add_argument('--timeframes', default='5m,15m,1h,4h,1d', help='Comma-separated timeframes')
    parser.add_argument('--hours', type=int, default=24, help='Hours to look back for gaps')
    parser.add_argument('--detect-only', action='store_true', help='Only detect gaps, do not fill')
    parser.add_argument('--fill-only', action='store_true', help='Skip detection, only fill known gaps')
    
    args = parser.parse_args()
    
    timeframes = [tf.strip() for tf in args.timeframes.split(',')]
    
    print("🔍 AI Trading Bot Gap Detection & Filling")
    print("=" * 50)
    print(f"Symbol: {args.symbol}")
    print(f"Timeframes: {', '.join(timeframes)}")
    print(f"Look back: {args.hours} hours")
    print(f"Mode: {'Detect only' if args.detect_only else 'Fill only' if args.fill_only else 'Detect & Fill'}")
    print()
    
    gap_detector = DataGapDetector()
    
    try:
        await gap_detector.initialize()
        
        if args.fill_only:
            # 단순히 gap filling 실행 (이미 알려진 모든 gaps 처리)
            total_filled = await gap_detector.check_and_fill_gaps(
                symbol=args.symbol,
                timeframes=timeframes,
                hours_back=args.hours
            )
            print(f"✅ Total records filled: {total_filled}")
            
        else:
            # 각 타임프레임별로 gaps 감지
            all_gaps = {}
            total_missing = 0
            
            for timeframe in timeframes:
                print(f"🔍 Checking {timeframe} gaps...")
                gaps = await gap_detector.detect_gaps(args.symbol, timeframe, args.hours)
                
                if gaps:
                    all_gaps[timeframe] = gaps
                    gap_count = sum(1 + (gap[1] - gap[0]) // gap_detector._get_expected_interval_ms(timeframe) for gap in gaps)
                    total_missing += gap_count
                    
                    print(f"  📊 Found {len(gaps)} gap ranges, ~{gap_count} missing candles")
                    
                    for i, (start_ts, end_ts) in enumerate(gaps[:3]):  # 처음 3개만 표시
                        start_time = datetime.fromtimestamp(start_ts / 1000)
                        end_time = datetime.fromtimestamp(end_ts / 1000)
                        print(f"    Gap {i+1}: {start_time.strftime('%m-%d %H:%M')} ~ {end_time.strftime('%m-%d %H:%M')}")
                    
                    if len(gaps) > 3:
                        print(f"    ... and {len(gaps) - 3} more gaps")
                else:
                    print(f"  ✅ No gaps found")
                print()
            
            if not all_gaps:
                print("🎉 No data gaps found across all timeframes!")
                return
            
            print(f"📊 Summary: {total_missing} missing candles across {len(all_gaps)} timeframes")
            
            if args.detect_only:
                print("🔍 Detection complete (fill disabled)")
                return
            
            # 사용자 확인
            response = input(f"\n🤔 Fill {total_missing} missing candles? [y/N]: ").lower().strip()
            if response not in ['y', 'yes']:
                print("❌ Gap filling cancelled")
                return
            
            # Gap 채우기
            print("\n📥 Filling gaps...")
            total_filled = 0
            
            for timeframe, gaps in all_gaps.items():
                print(f"📥 Filling {timeframe} gaps...")
                filled = await gap_detector.fill_gaps(args.symbol, timeframe, gaps)
                total_filled += filled
                print(f"  ✅ Filled {filled} candles")
            
            print(f"\n🎉 Gap filling complete! Total filled: {total_filled} candles")
            
            # 잠시 대기 후 검증
            print("\n⏳ Waiting for processor to handle queued data...")
            await asyncio.sleep(5)
            
            # 검증
            print("🔍 Verifying gap filling...")
            remaining_gaps = 0
            for timeframe in timeframes:
                gaps = await gap_detector.detect_gaps(args.symbol, timeframe, args.hours)
                if gaps:
                    gap_count = sum(1 + (gap[1] - gap[0]) // gap_detector._get_expected_interval_ms(timeframe) for gap in gaps)
                    remaining_gaps += gap_count
            
            if remaining_gaps == 0:
                print("✅ All gaps successfully filled!")
            else:
                print(f"⚠️  {remaining_gaps} gaps remain (may need processor to finish)")
    
    except KeyboardInterrupt:
        print("\n❌ Interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    finally:
        await gap_detector.close()
    
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))