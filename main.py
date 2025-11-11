import typer
import asyncssh
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

app = typer.Typer()

class AsyncSSHClient:
    def __init__(self):
        self.conn = None

    async def __aenter__(self):
        host = os.getenv("SSH_HOST")
        username = os.getenv("SSH_USER")
        port = int(os.getenv("SSH_PORT", "22"))
        password = os.getenv("SSH_PASSWORD")

        if not host:
            typer.secho("Error: SSH_HOST is required and cannot be empty.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        if not username:
            typer.secho("Error: SSH_USER is required and cannot be empty.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        if not password:
            typer.secho("Error: SSH_PASSWORD is required and cannot be empty.", fg=typer.colors.RED)
            raise typer.Exit(code=1)

        try:
            self.conn = await asyncssh.connect(
                host,
                port=port,
                username=username,
                password=password,
                known_hosts=None  # 相当于 paramiko 的 AutoAddPolicy
            )
            typer.secho("Connection successful.", fg=typer.colors.GREEN)
            return self.conn

        except asyncssh.PermissionDenied:
            typer.secho(
                "Authentication failed. Please check your credentials.",
                fg=typer.colors.RED
            )
            raise typer.Exit(code=1)
        except asyncssh.Error as e:
            typer.secho(f"SSH error occurred: {e}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        except Exception as e:
            typer.secho(f"Connection error: {e}", fg=typer.colors.RED)
            raise typer.Exit(code=1)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            typer.secho("Closing SSH connection.", fg=typer.colors.YELLOW)
            self.conn.close()

            # 等待连接关闭,设置超时避免卡住
            try:
                await asyncio.wait_for(self.conn.wait_closed(), timeout=2.0)
            except asyncio.TimeoutError:
                typer.secho("Warning: Connection close timeout", fg=typer.colors.YELLOW)

        return False


async def stream_log(log_file: str):
    process = None

    try:
        async with AsyncSSHClient() as conn:
            log_base_path = os.getenv("LOG_BASE_PATH", "")
            if log_base_path:
                target_log_file = f"{log_base_path}/{log_file}.log"
            else:
                target_log_file = f"{log_file}.log"

            command = f"tail -f {target_log_file}"
            typer.secho(f"Executing command: {command}", fg=typer.colors.CYAN)

            process = await conn.create_process(command)

            try:
                async for line in process.stdout:
                    print(line.strip())

            except asyncio.CancelledError:
                typer.secho("\n--- Stopping log stream... ---", fg=typer.colors.YELLOW)
                raise

    except asyncio.CancelledError:
        if process and not process.is_closing():
            process.kill()

            try:
                await asyncio.wait_for(process.wait_closed(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
        raise

    finally:
        if process and not process.is_closing():
            try:
                process.kill()
            except Exception:
                pass


@app.command()
def log(
        log_file: str = typer.Argument(..., help="日志文件名(不含 .log 后缀)"),
):
    try:
        asyncio.run(stream_log(log_file))
    except KeyboardInterrupt:
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"An unexpected error occurred: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.callback()
def callback():
    env_file = Path(".env")
    if not env_file.exists() or not env_file.is_file():
        typer.secho("错误: 未找到 .env 文件!", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    load_dotenv(dotenv_path=env_file)

if __name__ == "__main__":
    app()