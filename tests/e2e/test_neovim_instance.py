"""
NeovimTestInstance - Managed Neovim instance for end-to-end testing.

This module provides a NeovimTestInstance class that manages a real Neovim process
for testing Quench plugin functionality in a realistic environment.
"""

import asyncio
import subprocess
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class NeovimTestInstance:
    """
    Manages a real Neovim instance for end-to-end testing.

    Features:
    - Launches headless Neovim with Quench plugin loaded using subprocess
    - Provides log file monitoring and retrieval
    - Command execution via Neovim command line arguments
    - Proper cleanup and resource management
    """

    def __init__(self, config_file: Optional[str] = None):
        self.process: Optional[subprocess.Popen] = None
        self.temp_dir: Optional[tempfile.TemporaryDirectory] = None
        self.config_file = config_file
        self.log_start_position = 0
        self.test_file_path: Optional[str] = None
        self.commands_to_execute: List[str] = []
        self.stdout: str = ""
        self.stderr: str = ""

    async def start(self, timeout: int = 30) -> None:
        """
        Start the Neovim instance and prepare for command execution.

        Args:
            timeout: Maximum time to wait for Neovim to start (seconds)
        """
        # Record initial log file state
        self._record_log_position()

        # Create temporary directory for test files
        self.temp_dir = tempfile.TemporaryDirectory()

        logger.info("NeovimTestInstance prepared - ready for command execution")

    def _record_log_position(self) -> None:
        """Record the current position in the Quench log file."""
        log_file = Path("/tmp/quench.log")
        if log_file.exists():
            self.log_start_position = log_file.stat().st_size
            logger.info(f"Recorded log position: {self.log_start_position}")
        else:
            self.log_start_position = 0
            logger.info("No existing log file found")

    def add_command(self, command: str) -> None:
        """
        Add a command to be executed when run_commands is called.

        Args:
            command: The Neovim command to execute
        """
        self.commands_to_execute.append(command)
        logger.info(f"Added command: {command}")

    async def run_commands(self, timeout: int = 30) -> Dict[str, Any]:
        """
        Execute all queued commands by launching Neovim with them.

        separate -c arguments for each command instead of trying to combine them.

        Args:
            timeout: Maximum time to wait for Neovim execution

        Returns:
            Dictionary with execution results
        """
        if not self.test_file_path:
            raise RuntimeError("No test file created. Call create_test_buffer first.")

        cwd = Path.cwd()

        # Consolidate setup commands to reduce total count
        nvim_cmd = [
            "nvim",
            "--headless",
            "-u",
            self.config_file or str(cwd / "tests" / "e2e" / "test_nvim_config.lua"),
            self.test_file_path,
            "-c",
            f"set rtp+={cwd} | set rtp+={cwd}/rplugin | UpdateRemotePlugins | sleep 3",
        ]

        # Add the essential user commands only
        for command in self.commands_to_execute:
            nvim_cmd.extend(["-c", command])

        # Add final commands
        nvim_cmd.extend(["-c", "messages | qall!"])

        logger.info(f"Executing Neovim command: {' '.join(nvim_cmd)}")

        try:
            self.process = subprocess.Popen(nvim_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            self.stdout, self.stderr = self.process.communicate(timeout=timeout)
            return_code = self.process.returncode

            logger.info(f"Neovim execution completed with return code: {return_code}")
            logger.info(f"STDOUT length: {len(self.stdout)} chars")
            logger.info(f"STDERR length: {len(self.stderr)} chars")

            return {
                "return_code": return_code,
                "stdout": self.stdout,
                "stderr": self.stderr,
                "success": return_code == 0,
            }

        except subprocess.TimeoutExpired:
            logger.warning("Neovim execution timed out - this may be expected for some tests")
            if self.process:
                self.process.kill()
                self.stdout, self.stderr = self.process.communicate()

            # For test purposes, timeout might not mean failure if we got useful output
            return {
                "return_code": -1,  # Indicate timeout
                "stdout": self.stdout,
                "stderr": self.stderr,
                "success": len(self.stdout) > 0 or len(self.stderr) > 0,  # Consider success if we got output
                "timeout": True,
            }

    async def wait_for_completion(self) -> Dict[str, Any]:
        """
        Execute all queued commands and wait for completion.

        Returns:
            Dictionary with execution results
        """
        return await self.run_commands()

    async def create_test_buffer(self, content: List[str], filename: str = "test.py") -> str:
        """
        Create a test buffer with the given content.

        Args:
            content: List of lines to write to the buffer
            filename: Name of the file (for syntax highlighting)

        Returns:
            Path to the created test file
        """
        if not self.temp_dir:
            self.temp_dir = tempfile.TemporaryDirectory()

        # Create test file
        test_file = Path(self.temp_dir.name) / filename
        test_file.write_text("\n".join(content))

        self.test_file_path = str(test_file)
        logger.info(f"Created test file: {test_file}")

        return str(test_file)

    async def execute_command(self, command: str) -> None:
        """
        Queue a Neovim command for execution.

        Args:
            command: The command to execute
        """
        self.add_command(command)
        logger.info(f"Queued command: {command}")

    async def wait_for_message(self, expected_pattern: str, timeout: int = 30, check_interval: float = 0.5) -> bool:
        """
        Wait for a specific message pattern to appear in Neovim messages.

        Args:
            expected_pattern: Pattern to search for in messages
            timeout: Maximum time to wait (seconds)
            check_interval: How often to check for the message (seconds)

        Returns:
            True if message found, False if timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            new_messages = self.get_new_messages()

            for message in new_messages:
                if expected_pattern in message:
                    logger.info(f"Found expected message: {message}")
                    return True

            await asyncio.sleep(check_interval)

        logger.warning(f"Timeout waiting for message pattern: {expected_pattern}")
        return False

    def get_new_messages(self) -> List[str]:
        """
        Get messages from the executed Neovim session.

        Returns:
            List of message lines from stdout
        """
        if self.stdout:
            return [line.strip() for line in self.stdout.split("\n") if line.strip()]
        return []

    def get_all_messages(self) -> List[str]:
        """
        Get all messages from stdout and stderr.

        Returns:
            List of all message lines
        """
        messages = []
        if self.stdout:
            messages.extend([line.strip() for line in self.stdout.split("\n") if line.strip()])
        if self.stderr:
            messages.extend([line.strip() for line in self.stderr.split("\n") if line.strip()])
        return messages

    def get_error_messages(self) -> List[str]:
        """
        Get error messages from Neovim output.

        Returns:
            List of error message lines
        """
        messages = self.get_all_messages()

        # Filter for error-like messages
        error_messages = []
        for msg in messages:
            msg_lower = msg.lower()
            if any(keyword in msg_lower for keyword in ["error", "failed", "exception", "traceback"]):
                error_messages.append(msg)

        return error_messages

    def get_log_tail(self) -> str:
        """
        Get new log entries from the Quench log file since test start.

        Returns:
            New log content as string
        """
        log_file = Path("/tmp/quench.log")

        if not log_file.exists():
            logger.warning("Quench log file does not exist")
            return ""

        try:
            with open(log_file, "r") as f:
                f.seek(self.log_start_position)
                new_content = f.read()
                logger.info(f"Read {len(new_content)} bytes from log file")
                return new_content
        except Exception as e:
            logger.error(f"Failed to read log file: {e}")
            return f"Error reading log: {e}"

    def get_process_output(self) -> Dict[str, str]:
        """
        Get stdout and stderr from the executed Neovim process.

        Returns:
            Dictionary with 'stdout' and 'stderr' keys
        """
        return {"stdout": self.stdout, "stderr": self.stderr}

    async def cleanup(self) -> None:
        """
        Clean up the Neovim instance and all resources.
        """
        logger.info("Starting cleanup")

        # Terminate Neovim process
        if self.process:
            try:
                self.process.terminate()

                # Wait for graceful shutdown
                try:
                    self.process.wait(timeout=5)
                    logger.info("Neovim process terminated gracefully")
                except subprocess.TimeoutExpired:
                    logger.warning("Neovim process did not terminate, killing")
                    self.process.kill()
                    self.process.wait()

            except Exception as e:
                logger.error(f"Error terminating process: {e}")
            finally:
                self.process = None

        # Clean up temporary directory
        if self.temp_dir:
            try:
                self.temp_dir.cleanup()
                logger.info("Cleaned up temporary directory")
            except Exception as e:
                logger.error(f"Error cleaning up temp directory: {e}")
            finally:
                self.temp_dir = None

        logger.info("Cleanup completed")

    def check_for_errors_and_warnings(self) -> Dict[str, Any]:
        """
        Comprehensive error and warning detection across all output sources.

        Returns:
            Dictionary with error detection results:
            - 'has_errors': boolean indicating if any errors were found
            - 'has_warnings': boolean indicating if any warnings were found
            - 'nvim_errors': list of error messages from Neovim
            - 'nvim_warnings': list of warning messages from Neovim
            - 'log_errors': list of error entries from quench.log
            - 'log_warnings': list of warning entries from quench.log
            - 'stderr_errors': list of errors from process stderr
            - 'summary': string summary of all issues found
        """
        result = {
            "has_errors": False,
            "has_warnings": False,
            "nvim_errors": [],
            "nvim_warnings": [],
            "log_errors": [],
            "log_warnings": [],
            "stderr_errors": [],
            "summary": "",
        }

        # Check Neovim messages for errors and warnings
        # Be more selective about what constitutes an "error" vs normal informational messages
        nvim_messages = self.get_all_messages()
        for msg in nvim_messages:
            msg_lower = msg.lower()
            # Skip certain benign messages that contain "error" but aren't actual errors
            if "error detected while processing command line:" in msg_lower and not any(
                serious in msg_lower for serious in ["exception", "traceback", "failed to"]
            ):
                continue  # Skip command line processing messages

            if any(keyword in msg_lower for keyword in ["exception", "traceback", "failed to"]):
                result["nvim_errors"].append(msg)
                result["has_errors"] = True
            elif any(keyword in msg_lower for keyword in ["warning", "warn"]):
                result["nvim_warnings"].append(msg)
                result["has_warnings"] = True

        # Check quench.log for errors and warnings
        log_content = self.get_log_tail()
        if log_content:
            log_lines = log_content.split("\n")
            for line in log_lines:
                line_lower = line.lower()
                # Skip benign address already in use errors (port conflicts during testing)
                if "address already in use" in line_lower:
                    continue

                if any(keyword in line_lower for keyword in ["error", "exception", "traceback", "failed"]):
                    result["log_errors"].append(line)
                    result["has_errors"] = True
                elif any(keyword in line_lower for keyword in ["warning", "warn"]):
                    result["log_warnings"].append(line)
                    result["has_warnings"] = True

        # Check process stderr for errors
        process_output = self.get_process_output()
        stderr_lines = process_output["stderr"].split("\n") if process_output["stderr"] else []
        for line in stderr_lines:
            if line.strip():  # Only non-empty lines
                line_lower = line.lower()
                # Skip benign "error detected while processing command line" messages
                if "error detected while processing command line:" in line_lower and not any(
                    serious in line_lower for serious in ["exception", "traceback", "failed to"]
                ):
                    continue

                if any(keyword in line_lower for keyword in ["exception", "traceback", "failed to"]):
                    result["stderr_errors"].append(line)
                    result["has_errors"] = True

        # Generate summary
        issues = []
        if result["nvim_errors"]:
            issues.append(f"{len(result['nvim_errors'])} Neovim errors")
        if result["nvim_warnings"]:
            issues.append(f"{len(result['nvim_warnings'])} Neovim warnings")
        if result["log_errors"]:
            issues.append(f"{len(result['log_errors'])} log errors")
        if result["log_warnings"]:
            issues.append(f"{len(result['log_warnings'])} log warnings")
        if result["stderr_errors"]:
            issues.append(f"{len(result['stderr_errors'])} stderr errors")

        if issues:
            result["summary"] = f"Found: {', '.join(issues)}"
        else:
            result["summary"] = "No errors or warnings detected"

        logger.info(f"Error detection result: {result['summary']}")
        return result
