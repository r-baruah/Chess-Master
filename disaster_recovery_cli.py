#!/usr/bin/env python3
"""
Disaster Recovery CLI Management Tool
Command-line interface for managing the disaster recovery system
"""
import asyncio
import argparse
import json
import sys
import os
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.disaster_recovery_service import get_disaster_recovery_service

def print_status(message: str, status: str = "INFO"):
    """Print formatted status message"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    status_emoji = {
        "INFO": "ℹ️",
        "SUCCESS": "✅", 
        "ERROR": "❌",
        "WARNING": "⚠️",
        "CRITICAL": "🚨"
    }
    print(f"[{timestamp}] {status_emoji.get(status, 'ℹ️')} {message}")

async def status_command(args):
    """Get comprehensive system status"""
    try:
        print_status("Getting system status...")
        service = await get_disaster_recovery_service()
        status = await service.get_system_status()
        
        print("\\n" + "="*60)
        print("DISASTER RECOVERY SYSTEM STATUS")
        print("="*60)
        
        # Overall status
        overall_status = status.get('overall_status', 'unknown').upper()
        status_icon = {
            'HEALTHY': '✅',
            'DEGRADED': '⚠️', 
            'CRITICAL': '🚨',
            'UNKNOWN': '❓'
        }.get(overall_status, '❓')
        
        print(f"Overall Status: {status_icon} {overall_status}")
        print(f"Last Check: {status.get('last_check', 'N/A')}")
        print(f"Service Initialized: {'✅' if status.get('service_initialized') else '❌'}")
        print(f"Background Tasks: {status.get('background_tasks_running', 0)} running")
        
        # Component details
        components = status.get('components', {})
        
        if 'health_monitor' in components:
            health = components['health_monitor']
            print("\\n--- HEALTH MONITOR ---")
            print(f"Monitoring Active: {'✅' if health.get('monitoring_active') else '❌'}")
            
            if 'overall_health' in health:
                oh = health['overall_health']
                if oh.get('critical_components'):
                    print(f"Critical Components: {', '.join(oh['critical_components'])}")
                if oh.get('degraded_components'):
                    print(f"Degraded Components: {', '.join(oh['degraded_components'])}")
        
        if 'token_manager' in components:
            tokens = components['token_manager']
            print("\\n--- BOT TOKENS ---")
            active = tokens.get('active_token', {})
            print(f"Active Bot: @{active.get('username', 'unknown')} ({active.get('status', 'unknown')})")
            print(f"Error Count: {active.get('error_count', 0)}")
            print(f"Backup Tokens: {tokens.get('backup_tokens_count', 0)} total, {tokens.get('backup_tokens_healthy', 0)} healthy")
        
        if 'channel_permissions' in components:
            channels = components['channel_permissions']
            print("\\n--- CHANNEL PERMISSIONS ---")
            print(f"Total Channels: {channels.get('total_channels', 0)}")
            print(f"Verified: {channels.get('verified_channels', 0)}")
            print(f"Failed: {channels.get('failed_channels', 0)}")
            
        print("\\n" + "="*60)
        
    except Exception as e:
        print_status(f"Failed to get system status: {e}", "ERROR")
        sys.exit(1)

async def health_check_command(args):
    """Perform immediate health check"""
    try:
        print_status("Performing comprehensive health check...")
        service = await get_disaster_recovery_service()
        result = await service.perform_system_health_check()
        
        print("\\n" + "="*50)
        print("HEALTH CHECK RESULTS")
        print("="*50)
        
        print(f"Overall Status: {result.get('status', 'unknown').upper()}")
        print(f"Check Time: {result.get('timestamp', 'N/A')}")
        print(f"Message: {result.get('message', 'N/A')}")
        
        if result.get('components'):
            print("\\n--- COMPONENT STATUS ---")
            for component, status in result['components'].items():
                icon = '✅' if status == 'healthy' else '⚠️' if status == 'degraded' else '❌'
                print(f"{component}: {icon} {status}")
                
        if 'permission_sync' in result:
            sync = result['permission_sync']
            print("\\n--- PERMISSION SYNC ---")
            print(f"Tokens Checked: {sync.get('total_tokens', 0)}")
            print(f"Successful: {sync.get('successful_tokens', 0)}")
            print(f"Failed: {sync.get('failed_tokens', 0)}")
            
        print("\\n" + "="*50)
        print_status("Health check completed", "SUCCESS")
        
    except Exception as e:
        print_status(f"Health check failed: {e}", "ERROR")
        sys.exit(1)

async def create_backup_command(args):
    """Create recovery package"""
    try:
        print_status("Creating disaster recovery package...")
        service = await get_disaster_recovery_service()
        result = await service.create_recovery_package()
        
        if result['status'] == 'success':
            package = result['package']
            print_status(f"Recovery package created successfully!", "SUCCESS")
            print(f"Package ID: {package['package_id']}")
            print(f"Timestamp: {package['timestamp']}")
            print(f"Checksum: {package['checksum']}")
            
            # Save package info to file if requested
            if args.save:
                filename = f"recovery_{package['package_id']}.json"
                with open(filename, 'w') as f:
                    json.dump(package, f, indent=2, default=str)
                print_status(f"Package saved to {filename}", "SUCCESS")
        else:
            print_status(f"Failed to create recovery package: {result.get('message', 'Unknown error')}", "ERROR")
            sys.exit(1)
            
    except Exception as e:
        print_status(f"Failed to create recovery package: {e}", "ERROR")
        sys.exit(1)

async def restore_backup_command(args):
    """Restore from recovery package"""
    try:
        if not os.path.exists(args.package_file):
            print_status(f"Recovery package file not found: {args.package_file}", "ERROR")
            sys.exit(1)
            
        print_status("Loading recovery package...", "WARNING")
        
        with open(args.package_file, 'r') as f:
            recovery_package = json.load(f)
            
        if not args.confirm:
            print_status("This will perform emergency system recovery!", "WARNING")
            print(f"Package: {recovery_package.get('package_id', 'unknown')}")
            print(f"Created: {recovery_package.get('timestamp', 'unknown')}")
            confirm = input("Are you sure you want to proceed? (yes/no): ")
            if confirm.lower() != 'yes':
                print_status("Recovery cancelled", "INFO")
                return
                
        print_status("Executing emergency recovery...", "CRITICAL")
        service = await get_disaster_recovery_service()
        result = await service.execute_emergency_recovery(recovery_package)
        
        if result['status'] == 'success':
            print_status("Emergency recovery completed successfully!", "SUCCESS")
        else:
            print_status(f"Emergency recovery failed: {result.get('message', 'Unknown error')}", "ERROR")
            sys.exit(1)
            
    except Exception as e:
        print_status(f"Recovery execution failed: {e}", "ERROR")
        sys.exit(1)

async def failover_command(args):
    """Trigger bot token failover"""
    try:
        if not args.confirm:
            confirm = input("Trigger bot token failover? (yes/no): ")
            if confirm.lower() != 'yes':
                print_status("Failover cancelled", "INFO")
                return
                
        print_status("Triggering bot token failover...", "WARNING")
        service = await get_disaster_recovery_service()
        result = await service.trigger_bot_failover()
        
        if result['status'] == 'success':
            print_status("Bot failover completed successfully!", "SUCCESS")
        else:
            print_status(f"Bot failover failed: {result.get('message', 'Unknown error')}", "ERROR")
            sys.exit(1)
            
    except Exception as e:
        print_status(f"Failover failed: {e}", "ERROR")
        sys.exit(1)

async def sync_permissions_command(args):
    """Synchronize channel permissions"""
    try:
        print_status("Synchronizing channel permissions...")
        service = await get_disaster_recovery_service()
        result = await service.sync_channel_permissions()
        
        if result['status'] == 'success':
            sync_results = result['sync_results']
            print_status("Channel permissions synchronized!", "SUCCESS")
            print(f"Tokens Processed: {sync_results['total_tokens']}")
            print(f"Successful: {sync_results['successful_tokens']}")
            print(f"Failed: {sync_results['failed_tokens']}")
            
            if sync_results['token_results']:
                print("\\n--- TOKEN RESULTS ---")
                for token_result in sync_results['token_results']:
                    status_icon = '✅' if token_result['success'] else '❌'
                    print(f"{status_icon} @{token_result['bot_username']}")
                    if token_result['success']:
                        print(f"   Permissions: {token_result['successful_permissions']}/{token_result['total_permissions_tested']}")
                    else:
                        print(f"   Error: {token_result.get('error', 'Unknown')}")
        else:
            print_status(f"Permission sync failed: {result.get('message', 'Unknown error')}", "ERROR")
            sys.exit(1)
            
    except Exception as e:
        print_status(f"Permission sync failed: {e}", "ERROR")
        sys.exit(1)

async def events_command(args):
    """Show recent system events"""
    try:
        print_status(f"Getting recent events (last {args.hours} hours)...")
        service = await get_disaster_recovery_service()
        result = await service.get_recent_events(args.hours)
        
        if result['status'] == 'success':
            events = result['events']
            
            print("\\n" + "="*60)
            print("RECENT SYSTEM EVENTS")
            print("="*60)
            
            # Failover events
            if events.get('failover_events'):
                print("\\n--- FAILOVER EVENTS ---")
                for event in events['failover_events'][:10]:  # Show last 10
                    status_icon = '✅' if event['success'] else '❌'
                    print(f"{status_icon} {event['event_time']} - {event['event_type']}")
                    if event.get('reason'):
                        print(f"   Reason: {event['reason']}")
                    if event.get('recovery_time_seconds'):
                        print(f"   Recovery Time: {event['recovery_time_seconds']:.1f}s")
            
            # Health events
            if events.get('health_events'):
                print("\\n--- HEALTH EVENTS ---")
                for event in events['health_events'][:10]:  # Show last 10
                    status_icon = '🚨' if event['overall_status'] == 'critical' else '⚠️'
                    print(f"{status_icon} {event['check_time']} - {event['overall_status'].upper()}")
                    
            # Recent notifications
            if events.get('recent_notifications'):
                print("\\n--- RECENT NOTIFICATIONS ---")
                for notif in events['recent_notifications'][:10]:  # Show last 10
                    type_icon = {
                        'critical_system_failure': '🚨',
                        'failover_success': '✅',
                        'system_degradation': '⚠️',
                        'recovery_success': '✅',
                        'recovery_failure': '❌'
                    }.get(notif.get('type'), 'ℹ️')
                    print(f"{type_icon} {notif.get('timestamp', 'N/A')} - {notif.get('message', 'No message')}")
            
            print("\\n" + "="*60)
        else:
            print_status(f"Failed to get events: {result.get('message', 'Unknown error')}", "ERROR")
            sys.exit(1)
            
    except Exception as e:
        print_status(f"Failed to get events: {e}", "ERROR")
        sys.exit(1)

async def metrics_command(args):
    """Show performance metrics"""
    try:
        print_status("Getting performance metrics...")
        service = await get_disaster_recovery_service()
        result = await service.get_performance_metrics()
        
        if result['status'] == 'success':
            metrics = result['metrics']
            
            print("\\n" + "="*60)
            print("SYSTEM PERFORMANCE METRICS")
            print("="*60)
            
            # Availability metrics
            if 'availability_24h' in metrics:
                avail = metrics['availability_24h']
                print("\\n--- 24 HOUR AVAILABILITY ---")
                print(f"Healthy: {avail['healthy_percentage']:.1f}%")
                print(f"Degraded: {avail['degraded_percentage']:.1f}%")  
                print(f"Critical: {avail['critical_percentage']:.1f}%")
                
            # Failover statistics
            if 'failover_stats_7d' in metrics:
                failover = metrics['failover_stats_7d']
                print("\\n--- 7 DAY FAILOVER STATS ---")
                print(f"Total Failovers: {failover.get('total_failovers', 0)}")
                print(f"Successful: {failover.get('successful_failovers', 0)}")
                if failover.get('avg_recovery_time'):
                    print(f"Avg Recovery Time: {float(failover['avg_recovery_time']):.1f}s")
                    
            # Token health
            if 'token_health' in metrics:
                tokens = metrics['token_health']
                print("\\n--- BOT TOKEN HEALTH ---")
                print(f"Total Tokens: {tokens.get('total_tokens', 0)}")
                print(f"Active: {tokens.get('active_tokens', 0)}")
                print(f"Healthy: {tokens.get('healthy_tokens', 0)}")
                print(f"Degraded: {tokens.get('degraded_tokens', 0)}")
                print(f"Failed: {tokens.get('failed_tokens', 0)}")
                if tokens.get('avg_error_count'):
                    print(f"Avg Error Count: {float(tokens['avg_error_count']):.1f}")
                    
            print("\\n" + "="*60)
        else:
            print_status(f"Failed to get metrics: {result.get('message', 'Unknown error')}", "ERROR")
            sys.exit(1)
            
    except Exception as e:
        print_status(f"Failed to get metrics: {e}", "ERROR")
        sys.exit(1)

def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Disaster Recovery Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s status                    # Get system status
  %(prog)s health-check             # Perform health check  
  %(prog)s create-backup --save     # Create and save recovery package
  %(prog)s restore-backup package.json --confirm  # Restore from package
  %(prog)s failover --confirm       # Trigger bot failover
  %(prog)s sync-permissions         # Sync channel permissions
  %(prog)s events --hours 12        # Show events from last 12 hours
  %(prog)s metrics                  # Show performance metrics
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Get comprehensive system status')
    
    # Health check command
    health_parser = subparsers.add_parser('health-check', help='Perform immediate health check')
    
    # Create backup command
    backup_parser = subparsers.add_parser('create-backup', help='Create disaster recovery package')
    backup_parser.add_argument('--save', action='store_true', help='Save package to file')
    
    # Restore backup command
    restore_parser = subparsers.add_parser('restore-backup', help='Restore from recovery package')
    restore_parser.add_argument('package_file', help='Path to recovery package file')
    restore_parser.add_argument('--confirm', action='store_true', help='Skip confirmation prompt')
    
    # Failover command
    failover_parser = subparsers.add_parser('failover', help='Trigger bot token failover')
    failover_parser.add_argument('--confirm', action='store_true', help='Skip confirmation prompt')
    
    # Sync permissions command
    sync_parser = subparsers.add_parser('sync-permissions', help='Synchronize channel permissions')
    
    # Events command
    events_parser = subparsers.add_parser('events', help='Show recent system events')
    events_parser.add_argument('--hours', type=int, default=24, help='Hours to look back (default: 24)')
    
    # Metrics command
    metrics_parser = subparsers.add_parser('metrics', help='Show system performance metrics')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Command routing
    command_map = {
        'status': status_command,
        'health-check': health_check_command,
        'create-backup': create_backup_command,
        'restore-backup': restore_backup_command,
        'failover': failover_command,
        'sync-permissions': sync_permissions_command,
        'events': events_command,
        'metrics': metrics_command
    }
    
    command_func = command_map.get(args.command)
    if command_func:
        try:
            asyncio.run(command_func(args))
        except KeyboardInterrupt:
            print_status("Operation cancelled by user", "WARNING")
            sys.exit(1)
    else:
        print_status(f"Unknown command: {args.command}", "ERROR")
        parser.print_help()
        sys.exit(1)

if __name__ == '__main__':
    main()