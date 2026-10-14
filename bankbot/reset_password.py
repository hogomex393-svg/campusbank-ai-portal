"""Recover a local demo account using hidden terminal input, never an HTTP endpoint."""
import argparse
import getpass
import sqlite3
import sys
import warnings
from .config import ROOT, Settings
from .portal_store import PortalStore, PortalError


def main(argv=None):
    parser=argparse.ArgumentParser(description='Reset a CampusBank demo account password on the server computer.')
    parser.add_argument('--username',required=True,help='Existing login username, not the display name.')
    args=parser.parse_args(argv)
    path=Settings.load().database_path or ROOT/'logs/portal.sqlite3'
    if not path.is_file():
        print('找不到本机账户数据库，请在运行 CampusBank 的服务器电脑上操作。')
        return 1
    if not sys.stdin.isatty():
        print('请在交互式 PowerShell 终端中直接运行此命令；密码需要隐藏输入。')
        return 1
    try:
        store=PortalStore(path)
        with store.db() as c:
            user=c.execute('SELECT username FROM users WHERE username=?',(args.username.casefold(),)).fetchone()
        if not user:
            print('找不到这个用户名，请核对登录用户名。')
            return 1
        print('正在重置账户：'+user['username'])
        print('新密码输入时不会显示字符。账户权限、聊天记录和工单会保留。')
        with warnings.catch_warnings():
            warnings.simplefilter('error',getpass.GetPassWarning)
            password=getpass.getpass('请输入新密码（8 至 128 个字符）：')
            confirmation=getpass.getpass('请再次输入新密码：')
        if password!=confirmation:
            print('两次密码不一致，未修改。请重新运行命令。')
            return 1
        result=store.reset_password(user['username'],password)
        print('密码已重置，原登录已失效。请刷新网页，用新密码重新登录。')
        print('已退出旧登录数量：'+str(result['revoked_sessions']))
        return 0
    except (KeyboardInterrupt,EOFError):
        print('\n已取消，未修改密码。')
        return 1
    except getpass.GetPassWarning:
        print('此终端无法隐藏密码输入，未修改。请在电脑上的 PowerShell 中运行。')
        return 1
    except PortalError as exc:
        print(exc.message)
        return 1
    except sqlite3.Error:
        print('账户数据库暂时不可访问，未完成重置，请稍后重试。')
        return 1


if __name__=='__main__':
    raise SystemExit(main())
