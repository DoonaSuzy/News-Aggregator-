#!/usr/bin/env python3
"""
News Aggregator System Health Check Script
Check MySQL, Redis queue status, and article statistics for the last 24 hours
"""

import sys
from datetime import datetime, timedelta
from newsagg.repo import Repository
from newsagg.queue import StreamQueue
from newsagg.db import Database


def check_mysql_connection():
    """Check MySQL connection status"""
    print("=" * 60)
    print("*** MySQL Connection Check ***")
    print("=" * 60)
    
    try:
        db = Database()
        conn = db.connect()
        print("*** MySQL connection successful ***")
        conn.close()
        return True
    except Exception as e:
        print(f"*** MySQL connection failed: {e} ***")
        return False


def check_redis_connection():
    """Check Redis connection status"""
    print("\n" + "=" * 60)
    print("*** Redis Connection Check ***")
    print("=" * 60)
    
    try:
        queue = StreamQueue()
        queue.client.ping()
        print("*** Redis connection successful ***")
        return True
    except Exception as e:
        print(f"*** Redis connection failed: {e} ***")
        return False


def check_sources_status():
    """Check province source enabled status"""
    print("\n" + "=" * 60)
    print("*** Province Source Status ***")
    print("=" * 60)
    
    try:
        db = Database()
        conn = db.connect()
        repo = Repository()
        
        enabled_sources = repo.list_enabled_slots(conn)
        all_sources = repo.list_sources(conn)
        
        print(f"*** Total sources: {len(all_sources)} ***")
        print(f"*** Enabled sources: {len(enabled_sources)} ***")
        
        print("\n*** Enabled sources by province: ***")
        province_stats = {}
        
        for source in enabled_sources:
            province = source.get('province_code', 'Unknown')
            if province not in province_stats:
                province_stats[province] = []
            province_stats[province].append(source)
        
        for province, sources in province_stats.items():
            print(f"  *** {province}: {len(sources)} enabled sources ***")
            for source in sources:
                last_success = source.get('last_discovery_success_at_utc')
                status = "*** Normal ***" if last_success else "*** No success record ***"
                print(f"    - {source['adapter_name']} ({source['media_name']}) - {status}")
        
        # Check disabled sources
        disabled_sources = [s for s in all_sources if s['verification_status'] != 'enabled']
        if disabled_sources:
            print(f"\n*** Disabled sources: {len(disabled_sources)} ***")
            for source in disabled_sources[:5]:
                reason = source.get('pause_reason', 'Unknown reason')
                print(f"  - {source['adapter_name']} ({source['province_code']}) - {reason}")
            if len(disabled_sources) > 5:
                print(f"  ... and {len(disabled_sources) - 5} more disabled sources")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"*** Failed to check sources status: {e} ***")
        return False


def check_queue_status():
    """Check Redis queue status"""
    print("\n" + "=" * 60)
    print("*** Redis Queue Status ***")
    print("=" * 60)
    
    try:
        queue = StreamQueue()
        
        # Check queue backlog
        pending = queue.message_pending()
        pending_count = pending.get('pending', 0)
        
        print(f"*** Queue backlog messages: {pending_count} ***")
        
        if pending_count > 0:
            print("*** Queue has backlog! ***")
            # Try to read some pending messages
            pending_messages = queue.read_pending(count=min(5, pending_count))
            if pending_messages:
                print("*** Pending messages examples: ***")
                for msg in pending_messages[:3]:
                    print(f"  - Message ID: {msg.msg_id}, Job ID: {msg.job_id}")
        else:
            print("*** Queue has no backlog ***")
        
        return True
        
    except Exception as e:
        print(f"*** Failed to check queue status: {e} ***")
        return False


def generate_health_report():
    """Generate system health report"""
    print("\n" + "=" * 60)
    print("*** System Health Report ***")
    print("=" * 60)
    
    # Execute checks
    mysql_ok = check_mysql_connection()
    redis_ok = check_redis_connection()
    sources_ok = check_sources_status()
    queue_ok = check_queue_status()
    
    # Generate health score
    score = 0
    max_score = 4
    
    if mysql_ok:
        score += 1
    if redis_ok:
        score += 1
    if sources_ok:
        score += 1
    if queue_ok:
        score += 1
    
    percentage = (score / max_score) * 100
    
    print(f"\n*** System Health Score: {score}/{max_score} ({percentage:.1f}%) ***")
    
    if percentage >= 80:
        print("*** System is running well ***")
    elif percentage >= 60:
        print("*** System is mostly normal with some issues ***")
    else:
        print("*** System has serious problems and needs immediate attention ***")
    
    return score >= max_score * 0.8  # 80% or above is healthy


if __name__ == "__main__":
    print(">>> Starting News Aggregator System Health Check...")
    
    try:
        is_healthy = generate_health_report()
        print(f"\n>>> System health check completed")
        sys.exit(0 if is_healthy else 1)
    except Exception as e:
        print(f"\n>>> System health check failed: {e}")
        sys.exit(1)