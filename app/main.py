import argparse
import subprocess
import os
import sys
from pathlib import Path

# Add the project root to sys.path so we can import from 'app'
sys.path.append(str(Path(__file__).parent.parent))

from app import templates

def main():
    parser = argparse.ArgumentParser(description="Barrel Shortcut Runner")
    parser.add_argument("target", help="The path to the executable to run.")
    parser.add_argument("--template", help="The name of the template profile to use.")
    parser.add_argument("--runner", help="Override the runner from the template (e.g., wine).")
    parser.add_argument("--env", nargs='+', help="Override or add environment variables (e.g., --env DXVK_HUD=1).")
    parser.add_argument("--post-exec", help="Command to execute after the main process finishes.")
    parser.add_argument("--wait", action="store_true", help="Wait for user input after execution.")

    args = parser.parse_args()

    target_path = os.path.expanduser(args.target)

    if not os.path.exists(target_path):
        print(f"Error: Target path does not exist: {target_path}", file=sys.stderr)
        if args.wait:
            input("Apasă Enter pentru a închide...")
        sys.exit(1)

    # --- Settings Resolution ---
    final_runner = None
    final_env = {}
    parallel_cmd = None

    # 1. Load from template if provided
    if args.template:
        template_data = templates.get_template(args.template)
        if template_data:
            final_runner = template_data.get("runner")
            parallel_cmd = template_data.get("parallel_cmd")
            
            # Populate env from template
            for var in template_data.get("env", []):
                if '=' in var:
                    key, value = var.split('=', 1)
                    final_env[key] = value
                else:
                    final_env[var] = ""
    
    # 2. Apply explicit overrides from --env
    if args.env:
        for var in args.env:
            if '=' in var:
                key, value = var.split('=', 1)
                final_env[key] = value # Override or add
            else:
                final_env[var] = ""
    
    # 3. Apply explicit --runner override
    if args.runner:
        final_runner = args.runner

    # --- Execution ---
    
    # Prepare environment
    run_env = os.environ.copy()
    for key, value in final_env.items():
        # Expand user (~) and vars ($PREFIX, etc.)
        expanded_val = os.path.expandvars(os.path.expanduser(value))
        run_env[key] = expanded_val
        
    # Prepare command
    command = []
    if final_runner:
        command.append(final_runner)
    
    command.append(target_path)

    # --- Parallel Execution ---
    if parallel_cmd:
        try:
            print(f"Starting parallel command: {parallel_cmd}")
            subprocess.Popen(parallel_cmd, shell=True, env=run_env)
        except Exception as e:
            print(f"Error starting parallel command: {e}", file=sys.stderr)

    try:
        # Change to the executable's directory before running
        executable_dir = os.path.dirname(target_path)
        
        print(f"Running command: {' '.join(command)}")
        print(f"In directory: {executable_dir}")
        print(f"With environment: {final_env}")
        
        subprocess.run(command, env=run_env, cwd=executable_dir, check=True)

    except subprocess.CalledProcessError as e:
        print(f"Error executing '{' '.join(command)}': {e}", file=sys.stderr)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)

    # --- Post-Execution ---
    if args.post_exec:
        try:
            print(f"Running post-exec command: {args.post_exec}")
            subprocess.run(args.post_exec, shell=True, check=True)
        except Exception as e:
            print(f"Error in post-exec command: {e}", file=sys.stderr)

    if args.wait:
        input("Apasă Enter pentru a închide...")

if __name__ == "__main__":
    main()

