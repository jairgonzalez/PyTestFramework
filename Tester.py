import json
import subprocess
import pytest
import os
import time
from pathlib import Path
from datetime import datetime

# Global variables for logging
TEST_RUN_DIR = None
RESULT_LOG_FILE = None

def setup_logging():
    """Set up logging directory and files for this test run."""
    global TEST_RUN_DIR, RESULT_LOG_FILE
    
    # Only set up once
    if TEST_RUN_DIR is not None:
        return
    
    # Create logs directory if it doesn't exist
    logs_dir = Path(__file__).parent / "logs"
    logs_dir.mkdir(exist_ok=True)
    
    # Create timestamped directory for this test run
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    TEST_RUN_DIR = logs_dir / f"test_run_{timestamp}"
    TEST_RUN_DIR.mkdir(exist_ok=True)
    
    # Create result log file
    RESULT_LOG_FILE = TEST_RUN_DIR / "result.log"
    
    # Write initial log entry
    with open(RESULT_LOG_FILE, 'w') as f:
        f.write(f"Test Run Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 50 + "\n\n")
    
    print(f"Test logs will be saved to: {TEST_RUN_DIR}")

def log_test_result(test_name, script_path, result, expected_success, validation_error=None):
    """Log individual test result to both console and files."""
    global TEST_RUN_DIR, RESULT_LOG_FILE
    
    # Ensure logging is set up
    if TEST_RUN_DIR is None:
        setup_logging()
    
    # Create individual test log file
    safe_name = "".join(c for c in test_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    test_log_file = TEST_RUN_DIR / f"{safe_name.replace(' ', '_')}.log"
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Determine overall test status
    script_success = result['success'] == expected_success
    validation_success = validation_error is None
    overall_success = script_success and validation_success
    
    status = "PASSED" if overall_success else "FAILED"
    
    # Individual test log content
    test_log_content = f"""Test: {test_name}
Script: {script_path}
Timestamp: {timestamp}
Status: {status}
Expected Success: {expected_success}
Actual Success: {result['success']}
Return Code: {result['returncode']}
Execution Time: {result['execution_time']:.2f} seconds

STDOUT:
{result['stdout'] if result['stdout'] else '(no output)'}

STDERR:
{result['stderr'] if result['stderr'] else '(no errors)'}

"""
    
    # Add validation error details if present
    if validation_error:
        test_log_content += f"""
VALIDATION ERROR:
{validation_error}

"""
    
    test_log_content += "=" * 50 + "\n"
    
    # Write individual test log
    with open(test_log_file, 'w') as f:
        f.write(test_log_content)
    
    # Append to result log
    with open(RESULT_LOG_FILE, 'a') as f:
        f.write(f"[{timestamp}] {status}: {test_name}\n")
        f.write(f"  Script: {script_path}\n")
        f.write(f"  Execution Time: {result['execution_time']:.2f}s\n")
        f.write(f"  Return Code: {result['returncode']}\n")
        
        if not script_success:
            f.write(f"  Script Status: Expected {'success' if expected_success else 'failure'} but got {'success' if result['success'] else 'failure'}\n")
        
        if validation_error:
            f.write(f"  Validation Error: {validation_error.split(chr(10))[0]}...\n")
        
        if result['stderr']:
            f.write(f"  Error: {result['stderr'][:100]}...\n")
        f.write("\n")

def finalize_logging():
    """Write final summary to result log."""
    global RESULT_LOG_FILE
    
    if RESULT_LOG_FILE and RESULT_LOG_FILE.exists():
        with open(RESULT_LOG_FILE, 'a') as f:
            f.write("=" * 50 + "\n")
            f.write(f"Test Run Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

def load_test_cases():
    """Load test cases from Testcase.json file."""
    testcase_file = Path("Testcase.json")
    if not testcase_file.exists():
        # Try to find it relative to the script
        script_dir = Path(__file__).parent
        testcase_file = script_dir / "Testcase.json"
    
    try:
        with open(testcase_file, 'r') as f:
            test_cases = json.load(f)
            
        # Convert string test cases to dictionary format
        normalized_test_cases = []
        for tc in test_cases:
            if isinstance(tc, str):
                # If test case is just a string, treat it as a script path
                normalized_test_cases.append({
                    'name': f"Test {Path(tc).stem}",
                    'script_path': tc
                })
            else:
                normalized_test_cases.append(tc)
                
        return normalized_test_cases
    except FileNotFoundError:
        pytest.fail(f"Testcase.json file not found at {testcase_file}")
    except json.JSONDecodeError:
        pytest.fail(f"Testcase.json at {testcase_file} contains invalid JSON")

def pytest_generate_tests(metafunc):
    """Generate test cases dynamically."""
    if "test_case" in metafunc.fixturenames:
        test_cases = load_test_cases()
        # Add test_id to provide better names for parameterized tests
        ids = []
        for i, tc in enumerate(test_cases):
            if isinstance(tc, dict):
                ids.append(tc.get('name', f"test_{i}"))
            else:
                ids.append(f"test_{i}")
                
        metafunc.parametrize("test_case", test_cases, ids=ids)

def execute_bash_script(script_path, timeout=30):
    """Execute a bash script and return the result."""
    script_path = Path(script_path)
    if not script_path.is_absolute():
        # If relative path, try to resolve from the script directory first
        script_dir = Path(__file__).parent
        full_path = script_dir / script_path
        if full_path.exists():
            script_path = full_path
    
    try:
        # Make sure the script is executable
        script_path.chmod(0o755)
        
        # Run the script with timeout
        start_time = time.time()
        result = subprocess.run(['bash', str(script_path)], 
                                capture_output=True, 
                                text=True, 
                                check=False,
                                timeout=timeout)
        execution_time = time.time() - start_time
        
        return {
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'execution_time': execution_time,
            'success': result.returncode == 0
        }
    except subprocess.TimeoutExpired:
        return {
            'returncode': -1,
            'stdout': '',
            'stderr': f'Script execution timed out after {timeout} seconds',
            'execution_time': timeout,
            'success': False
        }
    except Exception as e:
        return {
            'returncode': -1,
            'stdout': '',
            'stderr': str(e),
            'execution_time': 0,
            'success': False
        }

def test_bash_script(test_case):
    """Test running a bash script and verify the results."""
    name = test_case.get('name', 'Unnamed test')
    script_path = test_case.get('script_path')
    expected_success = test_case.get('expected_success', True)
    timeout = test_case.get('timeout', 30)
    
    assert script_path is not None, f"No script path specified for test {name}"
    
    script_path = Path(script_path)
    # If it's a relative path, try resolving from script directory
    if not script_path.is_absolute():
        script_dir = Path(__file__).parent
        full_path = script_dir / script_path
        if full_path.exists():
            script_path = full_path
        else:
            # Try with .sh extension
            full_path_sh = script_dir / f"{script_path}.sh"
            if full_path_sh.exists():
                script_path = full_path_sh
    
    assert script_path.exists(), f"Script {script_path} not found for test {name}. Checked paths: {script_path}, {script_dir / script_path}"
    
    result = execute_bash_script(script_path, timeout)
    
    validation_error = None
    
    # Verify expected success/failure
    assert result['success'] == expected_success, (
        f"Test {name} {'failed' if expected_success else 'succeeded'} "
        f"but was expected to {'succeed' if expected_success else 'fail'}."
    )
    
    # Additional custom assertions based on test_case parameters
    if 'expected_output' in test_case and test_case['expected_output']:
        try:
            assert test_case['expected_output'] in result['stdout'], (
                f"Expected output '{test_case['expected_output']}' not found in script output"
            )
        except AssertionError as e:
            validation_error = str(e)
    
    # Check expected output from result file
    if 'expected_result_file' in test_case and test_case['expected_result_file']:
        expected_result_file = Path(test_case['expected_result_file'])
        if not expected_result_file.is_absolute():
            script_dir = Path(__file__).parent
            expected_result_file = script_dir / expected_result_file
        
        if expected_result_file.exists():
            with open(expected_result_file, 'r') as f:
                expected_content = f.read().strip()
            
            actual_output = result['stdout'].strip()
            try:
                assert expected_content == actual_output, (
                    f"Expected output from {test_case['expected_result_file']} does not match actual output.\n"
                    f"Expected:\n{expected_content}\n"
                    f"Actual:\n{actual_output}"
                )
            except AssertionError as e:
                validation_error = str(e)
        else:
            validation_error = f"Expected result file {expected_result_file} not found"
    
    # Log the test result with validation error if any
    log_test_result(name, script_path, result, expected_success, validation_error)
    
    # Re-raise validation error to fail the test
    if validation_error:
        raise AssertionError(validation_error)

def pytest_configure(config):
    """Called before test collection starts."""
    setup_logging()

def pytest_unconfigure(config):
    """Called after test collection finishes."""
    finalize_logging()

if __name__ == "__main__":
    pytest.main(["-v", __file__])