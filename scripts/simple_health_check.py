#!/usr/bin/env python3
"""
Simple News Aggregator System Health Check Script
"""

import sys
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
    """Check basic sources status"""
    print("\n" + "=" * 60)
    print("*** Sources Status Check ***")
    print("=" * 60)
    
    try:
        db = Database()
        conn = db.connect()
        
        # Try basic query
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as total FROM sources")
            total_result = cur.fetchone()
            total_sources = total_result['total'] if total_result else 0
            
            cur.execute("SELECT COUNT(*) as enabled FROM sources WHERE verification_status = 'enabled'")
            enabled_result = cur.fetchone()
            enabled_sources = enabled_result['enabled'] if enabled_result else 0
            
            cur.execute("SELECT COUNT(*) as disabled FROM sources WHERE verification_status != 'enabled'")
            disabled_result = cur.fetchone()
            disabled_sources = disabled_result['disabled'] if disabled_result else 0
        
        print(f"*** Total sources: {total_sources} ***")
        print(f"*** Enabled sources: {enabled_sources} ***")
        print(f"*** Disabled sources: {disabled_sources} ***")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"*** Failed to check sources status: {e} ***")
        return False


def check_queue_status():
    """Check Redis queue status"""
    print("\n" + "=" * 60)
    print("*** Queue Status Check ***")
    print("=" * 60)
    
    try:
        queue = StreamQueue()
        
        # Check queue backlog
        pending = queue.message_pending()
        pending_count = pending.get('pending', 0)
        
        print(f"*** Queue backlog messages: {pending_count} ***")
        
        if pending_count > 0:
            print("*** Queue has backlog! ***")
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