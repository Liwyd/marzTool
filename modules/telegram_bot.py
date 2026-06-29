import asyncio
import json
import logging
import sys
import threading
from pathlib import Path


class TelegramBot:
    def __init__(self, config, logger: logging.Logger = None):
        self.config = config
        self.log = logger or logging.getLogger("telegram_bot")
        self.app = None
        self._thread = None
        self._loop = None

    def start(self):
        if not self.config.get_telegram_enabled():
            return False

        token = self.config.get_telegram_token()
        admin_id = self.config.get_telegram_admin_id()

        if not token or not admin_id:
            self.log.warning("Telegram enabled but token/admin_id not set")
            return False

        if self._thread and self._thread.is_alive():
            self.log.info("Telegram bot already running")
            return True

        try:
            from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
            from telegram.ext import (
                ApplicationBuilder,
                CommandHandler,
                CallbackQueryHandler,
                ContextTypes,
                ConversationHandler,
                MessageHandler,
                filters,
            )
        except ImportError as e:
            self.log.error("python-telegram-bot not installed (python=%s): %s", sys.executable, e)
            self.log.error("Install it: %s -m pip install \"python-telegram-bot[job-queue]\"", sys.executable)
            return False

        try:
            DB_PATH = str(Path(__file__).parent.parent / "marztool.db")

            def _db():
                from modules.database import Database
                return Database(DB_PATH)

            def _cfg():
                from modules.config import Config
                return Config(_db())

            def is_auth(uid: int) -> bool:
                c = _cfg()
                ok = str(uid) == str(c.get_telegram_admin_id())
                c.db.close()
                return ok

            def is_sub(uid: int) -> bool:
                d = _db()
                sa = d.get_sub_admin(uid)
                d.close()
                return sa is not None

            def sub_scope(uid: int) -> list:
                d = _db()
                sa = d.get_sub_admin(uid)
                d.close()
                if sa:
                    return json.loads(sa.get("allowed_admins", "[]"))
                return []

            BG = "\U0001f7e2"
            RD = "\U0001f534"
            BL = "\U0001f535"
            CY = "\U0001f4a0"
            PK = "\U0001f49c"
            GY = "\u26aa"
            BM = "\U0001f6e1"

            def admin_menu_kb():
                c = _cfg()
                ct_on = c.get_counter_enabled()
                vc_on = c.get_vcounter_enabled()
                c.db.close()
                ct_label = f"{CY} Counter" if ct_on else f"{GY} Counter"
                vc_label = f"{BL} VCounter" if vc_on else f"{GY} VCounter"
                kb = [
                    [InlineKeyboardButton(ct_label, callback_data="menu_counter"),
                     InlineKeyboardButton(vc_label, callback_data="menu_vcounter")],
                    [InlineKeyboardButton(f"{PK} IP Manager", callback_data="menu_ip"),
                     InlineKeyboardButton(f"{BM} Volume", callback_data="menu_volume")],
                    [InlineKeyboardButton(f"{GY} Sub-Admins", callback_data="menu_subadmin")],
                    [InlineKeyboardButton(f"{BL} Daemon", callback_data="menu_daemon")],
                ]
                return InlineKeyboardMarkup(kb)

            def counter_menu_kb():
                kb = [
                    [InlineKeyboardButton("View Count", callback_data="count_view"),
                     InlineKeyboardButton("Full Report", callback_data="count_report")],
                    [InlineKeyboardButton("Settle (Reset My Count)", callback_data="count_settle")],
                    [InlineKeyboardButton("View Settlements", callback_data="count_settlements")],
                    [InlineKeyboardButton("Reset Counter", callback_data="count_reset")],
                    [InlineKeyboardButton("Back", callback_data="menu_main")],
                ]
                return InlineKeyboardMarkup(kb)

            def vcounter_menu_kb():
                kb = [
                    [InlineKeyboardButton("View Volume", callback_data="vc_view"),
                     InlineKeyboardButton("Full Report", callback_data="vc_report")],
                    [InlineKeyboardButton("Settle (Reset My Volume)", callback_data="vc_settle")],
                    [InlineKeyboardButton("View Settlements", callback_data="vc_settlements")],
                    [InlineKeyboardButton("Reset VCounter", callback_data="vc_reset")],
                    [InlineKeyboardButton("Back", callback_data="menu_main")],
                ]
                return InlineKeyboardMarkup(kb)

            def ip_menu_kb():
                kb = [
                    [InlineKeyboardButton("Tracked Users", callback_data="ip_users")],
                    [InlineKeyboardButton("Banned IPs", callback_data="ip_banned")],
                    [InlineKeyboardButton("Unban All", callback_data="ip_unban")],
                    [InlineKeyboardButton("Back", callback_data="menu_main")],
                ]
                return InlineKeyboardMarkup(kb)

            def subadmin_menu_kb():
                kb = [
                    [InlineKeyboardButton("List Counter Sub-Admins", callback_data="sa_list")],
                    [InlineKeyboardButton("Add Counter Sub-Admin", callback_data="sa_add")],
                    [InlineKeyboardButton("Remove Counter Sub-Admin", callback_data="sa_remove")],
                    [InlineKeyboardButton("Add Panel Admin", callback_data="sa_add_panel")],
                    [InlineKeyboardButton("Remove Panel Admin", callback_data="sa_rm_panel")],
                    [InlineKeyboardButton("---", callback_data="noop")],
                    [InlineKeyboardButton("List VC Sub-Admins", callback_data="vc_sa_list")],
                    [InlineKeyboardButton("Add VC Sub-Admin", callback_data="vc_sa_add")],
                    [InlineKeyboardButton("Remove VC Sub-Admin", callback_data="vc_sa_remove")],
                    [InlineKeyboardButton("Add VC Panel Admin", callback_data="vc_sa_add_panel")],
                    [InlineKeyboardButton("Remove VC Panel Admin", callback_data="vc_sa_rm_panel")],
                    [InlineKeyboardButton("Back", callback_data="menu_main")],
                ]
                return InlineKeyboardMarkup(kb)

            def daemon_menu_kb():
                from modules.daemon import daemon_pid
                pid = daemon_pid()
                status = f"{BG} Running (PID {pid})" if pid else f"{RD} Stopped"
                kb = [
                    [InlineKeyboardButton(f"Status: {status}", callback_data="noop")],
                    [InlineKeyboardButton("View Logs", callback_data="daemon_logs")],
                    [InlineKeyboardButton("Back", callback_data="menu_main")],
                ]
                return InlineKeyboardMarkup(kb)

            async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                uid = update.effective_user.id
                name = update.effective_user.first_name or "User"
                if is_auth(uid):
                    text = (
                        f"{CY} MarzTool Bot{GY}\n"
                        f"{'='*28}\n\n"
                        f"Welcome {BG} {name}{GY}!\n"
                        f"Role: {BG} Main Admin\n\n"
                        f"Tap a button below:"
                    )
                    await update.message.reply_text(text, reply_markup=admin_menu_kb())
                elif is_sub(uid) or is_vcounter_sub(uid):
                    kb = [
                        [InlineKeyboardButton(f"{CY} Counter", callback_data="count_view"),
                         InlineKeyboardButton(f"{BL} VCounter", callback_data="vc_view")],
                        [InlineKeyboardButton("Full Report", callback_data="count_report")],
                        [InlineKeyboardButton("Settle (Reset My Count)", callback_data="count_settle")],
                        [InlineKeyboardButton("Settle (Reset My Volume)", callback_data="vc_settle")],
                        [InlineKeyboardButton("View Settlements", callback_data="count_settlements")],
                    ]
                    text = (
                        f"{CY} MarzTool Bot{GY}\n"
                        f"{'='*28}\n\n"
                        f"Welcome {name}!\n"
                        f"Role: {BL} Sub-Admin\n\n"
                        f"Tap a button below:"
                    )
                    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
                else:
                    await update.message.reply_text(f"{RD} Unauthorized.")

            async def count_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                uid = update.effective_user.id
                d = _db()
                try:
                    from modules.counter import Counter
                    counter = Counter(None, d)
                    viewer_key = f"tg_{uid}"
                    if is_auth(uid):
                        report = counter.get_report(viewer=viewer_key)
                    elif is_sub(uid):
                        scope = sub_scope(uid)
                        if scope:
                            report = counter.get_report(admin_username=scope[0], viewer=viewer_key)
                        else:
                            report = {"admins": [], "total": 0}
                    else:
                        await update.message.reply_text(f"{RD} Unauthorized.")
                        return
                    if not report["admins"]:
                        await update.message.reply_text(f"{GY} No counts yet.")
                        return
                    lines = [f"  {u['admin_username']}:  {u['total_count']}" for u in report["admins"]]
                    text = (
                        f"{CY} Counter by Admin\n{'-'*24}\n"
                        + "\n".join(lines) +
                        f"\n{'-'*24}\n  Total: {report['total']}"
                    )
                    await update.message.reply_text(text)
                finally:
                    d.close()

            async def report_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                uid = update.effective_user.id
                d = _db()
                try:
                    from modules.counter import Counter
                    counter = Counter(None, d)
                    viewer_key = f"tg_{uid}"
                    if is_auth(uid):
                        report = counter.get_report(viewer=viewer_key)
                    elif is_sub(uid):
                        scope = sub_scope(uid)
                        if scope:
                            report = counter.get_report(admin_username=scope[0], viewer=viewer_key)
                        else:
                            report = {"admins": [], "total": 0}
                    else:
                        await update.message.reply_text(f"{RD} Unauthorized.")
                        return
                    if not report["admins"]:
                        await update.message.reply_text(f"{GY} No data.")
                        return
                    lines = [f"  {u['admin_username']}:  {u['total_count']}" for u in report["admins"]]
                    text = (
                        f"{CY} === Report ===\n\n"
                        + "\n".join(lines) +
                        f"\n\n  {BG}Total: {report['total']}"
                    )
                    await update.message.reply_text(text)
                finally:
                    d.close()

            async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                from modules.daemon import daemon_pid
                pid = daemon_pid()
                if pid:
                    text = f"{BG} Daemon: Running\n  PID: {pid}"
                else:
                    text = f"{RD} Daemon: Stopped"
                await update.message.reply_text(text)

            async def logs_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                from modules.daemon import LOG_FILE
                if not LOG_FILE.exists():
                    await update.message.reply_text(f"{GY} No logs yet.")
                    return
                with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()[-15:]
                text = f"{CY} Recent Logs\n{'-'*30}\n" + "".join(lines)
                if len(text) > 3900:
                    text = text[-3900:]
                await update.message.reply_text(text or f"{GY} Empty.")

            async def users_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                d = _db()
                try:
                    tracked = d.get_all_tracked_users()
                    if not tracked:
                        await update.message.reply_text(f"{GY} No tracked users.")
                        return
                    lines = [f"  {t['email']}:  {len(t['ips'])} IPs" for t in tracked[:20]]
                    text = f"{CY} Tracked Users\n{'-'*30}\n" + "\n".join(lines)
                    await update.message.reply_text(text)
                finally:
                    d.close()

            async def ban_list_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                bp = Path(__file__).parent.parent / "blocked_ips.csv"
                if not bp.exists():
                    await update.message.reply_text(f"{GY} No banned IPs.")
                    return
                content = bp.read_text().strip()
                if not content:
                    await update.message.reply_text(f"{GY} No banned IPs.")
                    return
                ips = [l.split(",")[0] for l in content.split("\n") if l.strip()]
                text = f"{RD} Banned IPs\n{'-'*30}\n" + "\n".join(f"  {ip}" for ip in ips[:20])
                await update.message.reply_text(text)

            async def unban_all_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                import subprocess
                try:
                    subprocess.run(["iptables", "-F"], capture_output=True, timeout=10)
                    bp = Path(__file__).parent.parent / "blocked_ips.csv"
                    bp.write_text("")
                    await update.message.reply_text(f"{BG} All IPs unbanned.")
                except Exception as e:
                    await update.message.reply_text(f"{RD} Error: {e}")

            async def count_reset_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                uid = update.effective_user.id
                if not is_auth(uid):
                    await update.message.reply_text(f"{RD} Only main admin.")
                    return
                d = _db()
                try:
                    d.reset_all_counters()
                finally:
                    d.close()
                await update.message.reply_text(f"{BG} All counters reset.")

            async def sa_list_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                d = _db()
                try:
                    subs = d.get_all_sub_admins()
                    if not subs:
                        await update.message.reply_text(f"{GY} No sub-admins.")
                        return
                    lines = []
                    for s in subs:
                        allowed = json.loads(s.get("allowed_admins", "[]"))
                        lines.append(f"  ID: {s['telegram_id']}\n  Can view: {', '.join(allowed)}")
                    text = f"{BL} Sub-Admins\n{'='*30}\n\n" + "\n\n".join(lines)
                    await update.message.reply_text(text)
                finally:
                    d.close()

            SA_ADD_ID, SA_ADD_SCOPE = range(2)

            async def sa_add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                if not is_auth(update.effective_user.id):
                    await update.message.reply_text(f"{RD} Unauthorized.")
                    return ConversationHandler.END
                await update.message.reply_text(f"{BL} Send the sub-admin's numeric Telegram ID:")
                return SA_ADD_ID

            async def sa_add_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                try:
                    sub_id = int(update.message.text.strip())
                except ValueError:
                    await update.message.reply_text(f"{RD} Invalid. Send a number:")
                    return SA_ADD_ID
                ctx.user_data["sa_id"] = sub_id
                await update.message.reply_text(
                    f"{BL} Send Marzban admin usernames (comma separated):\nExample: admin1,admin2"
                )
                return SA_ADD_SCOPE

            async def sa_add_scope(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                admins = [a.strip() for a in update.message.text.split(",") if a.strip()]
                if not admins:
                    await update.message.reply_text(f"{RD} No admins. Try again:")
                    return SA_ADD_SCOPE
                sub_id = ctx.user_data["sa_id"]
                d = _db()
                try:
                    d.add_sub_admin(sub_id, admins)
                finally:
                    d.close()
                await update.message.reply_text(
                    f"{BG} Sub-admin {sub_id} added.\nCan view: {', '.join(admins)}"
                )
                return ConversationHandler.END

            async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                await update.message.reply_text(f"{GY} Cancelled.")
                return ConversationHandler.END

            sa_add_conv = ConversationHandler(
                entry_points=[CommandHandler("add_subadmin", sa_add_start)],
                states={
                    SA_ADD_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, sa_add_id)],
                    SA_ADD_SCOPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sa_add_scope)],
                },
                fallbacks=[CommandHandler("cancel", cancel)],
            )

            async def sa_remove_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                if not is_auth(update.effective_user.id):
                    await update.message.reply_text(f"{RD} Unauthorized.")
                    return
                if not ctx.args:
                    await update.message.reply_text(f"{RD} Usage: /remove_subadmin <id>")
                    return
                try:
                    sub_id = int(ctx.args[0])
                except ValueError:
                    await update.message.reply_text(f"{RD} Invalid ID.")
                    return
                d = _db()
                try:
                    d.remove_sub_admin(sub_id)
                finally:
                    d.close()
                await update.message.reply_text(f"{BG} Sub-admin {sub_id} removed.")

            PA_ADD_ID, PA_ADD_SCOPE = range(2, 4)

            async def pa_add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                if not is_auth(update.effective_user.id):
                    await update.message.reply_text(f"{RD} Unauthorized.")
                    return ConversationHandler.END
                await update.message.reply_text(f"{BL} Send sub-admin's Telegram ID:")
                return PA_ADD_ID

            async def pa_add_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                try:
                    sub_id = int(update.message.text.strip())
                except ValueError:
                    await update.message.reply_text(f"{RD} Invalid. Send a number:")
                    return PA_ADD_ID
                ctx.user_data["pa_sub_id"] = sub_id
                await update.message.reply_text(f"{BL} Send panel admin usernames (comma separated):")
                return PA_ADD_SCOPE

            async def pa_add_scope(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                new_admins = [a.strip() for a in update.message.text.split(",") if a.strip()]
                if not new_admins:
                    await update.message.reply_text(f"{RD} No admins. Try again:")
                    return PA_ADD_SCOPE
                sub_id = ctx.user_data["pa_sub_id"]
                d = _db()
                try:
                    sa = d.get_sub_admin(sub_id)
                    if not sa:
                        await update.message.reply_text(f"{RD} Sub-admin {sub_id} not found.")
                        return ConversationHandler.END
                    current = json.loads(sa.get("allowed_admins", "[]"))
                    merged = list(dict.fromkeys(current + new_admins))
                    d.update_sub_admin_scope(sub_id, merged)
                finally:
                    d.close()
                await update.message.reply_text(f"{BG} Updated.\nCan view: {', '.join(merged)}")
                return ConversationHandler.END

            pa_add_conv = ConversationHandler(
                entry_points=[CommandHandler("add_panel_admin", pa_add_start)],
                states={
                    PA_ADD_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, pa_add_id)],
                    PA_ADD_SCOPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, pa_add_scope)],
                },
                fallbacks=[CommandHandler("cancel", cancel)],
            )

            PA_RM_ID, PA_RM_SCOPE = range(4, 6)

            async def pa_rm_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                if not is_auth(update.effective_user.id):
                    await update.message.reply_text(f"{RD} Unauthorized.")
                    return ConversationHandler.END
                await update.message.reply_text(f"{BL} Send sub-admin's Telegram ID:")
                return PA_RM_ID

            async def pa_rm_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                try:
                    sub_id = int(update.message.text.strip())
                except ValueError:
                    await update.message.reply_text(f"{RD} Invalid. Send a number:")
                    return PA_RM_ID
                ctx.user_data["pa_rm_sub_id"] = sub_id
                await update.message.reply_text(f"{BL} Send panel admin usernames to REMOVE (comma separated):")
                return PA_RM_SCOPE

            async def pa_rm_scope(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                rm = [a.strip() for a in update.message.text.split(",") if a.strip()]
                if not rm:
                    await update.message.reply_text(f"{RD} No admins. Try again:")
                    return PA_RM_SCOPE
                sub_id = ctx.user_data["pa_rm_sub_id"]
                d = _db()
                try:
                    sa = d.get_sub_admin(sub_id)
                    if not sa:
                        await update.message.reply_text(f"{RD} Sub-admin {sub_id} not found.")
                        return ConversationHandler.END
                    current = json.loads(sa.get("allowed_admins", "[]"))
                    remaining = [a for a in current if a not in rm]
                    d.update_sub_admin_scope(sub_id, remaining)
                finally:
                    d.close()
                await update.message.reply_text(
                    f"{BG} Updated.\nCan view: {', '.join(remaining) if remaining else 'none'}"
                )
                return ConversationHandler.END

            pa_rm_conv = ConversationHandler(
                entry_points=[CommandHandler("remove_panel_admin", pa_rm_start)],
                states={
                    PA_RM_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, pa_rm_id)],
                    PA_RM_SCOPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, pa_rm_scope)],
                },
                fallbacks=[CommandHandler("cancel", cancel)],
            )

            def is_vcounter_sub(uid: int) -> bool:
                d = _db()
                sa = d.get_vcounter_sub_admin(uid)
                d.close()
                return sa is not None

            def vcounter_sub_scope(uid: int) -> list:
                d = _db()
                sa = d.get_vcounter_sub_admin(uid)
                d.close()
                if sa:
                    return json.loads(sa.get("allowed_admins", "[]"))
                return []

            async def vc_sa_list_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                d = _db()
                try:
                    subs = d.get_all_vcounter_sub_admins()
                    if not subs:
                        await update.message.reply_text(f"{GY} No vcounter sub-admins.")
                        return
                    lines = []
                    for s in subs:
                        allowed = json.loads(s.get("allowed_admins", "[]"))
                        lines.append(f"  ID: {s['telegram_id']}\n  Can view: {', '.join(allowed)}")
                    text = f"{BL} VCounter Sub-Admins\n{'='*30}\n\n" + "\n\n".join(lines)
                    await update.message.reply_text(text)
                finally:
                    d.close()

            VC_SA_ADD_ID, VC_SA_ADD_SCOPE = range(6, 8)

            async def vc_sa_add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                if not is_auth(update.effective_user.id):
                    await update.message.reply_text(f"{RD} Unauthorized.")
                    return ConversationHandler.END
                await update.message.reply_text(f"{BL} Send the vcounter sub-admin's numeric Telegram ID:")
                return VC_SA_ADD_ID

            async def vc_sa_add_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                try:
                    sub_id = int(update.message.text.strip())
                except ValueError:
                    await update.message.reply_text(f"{RD} Invalid. Send a number:")
                    return VC_SA_ADD_ID
                ctx.user_data["vc_sa_id"] = sub_id
                await update.message.reply_text(
                    f"{BL} Send Marzban admin usernames (comma separated):\nExample: admin1,admin2"
                )
                return VC_SA_ADD_SCOPE

            async def vc_sa_add_scope(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                admins = [a.strip() for a in update.message.text.split(",") if a.strip()]
                if not admins:
                    await update.message.reply_text(f"{RD} No admins. Try again:")
                    return VC_SA_ADD_SCOPE
                sub_id = ctx.user_data["vc_sa_id"]
                d = _db()
                try:
                    d.add_vcounter_sub_admin(sub_id, admins)
                finally:
                    d.close()
                await update.message.reply_text(
                    f"{BG} VCounter sub-admin {sub_id} added.\nCan view: {', '.join(admins)}"
                )
                return ConversationHandler.END

            vc_sa_add_conv = ConversationHandler(
                entry_points=[CommandHandler("vc_add_subadmin", vc_sa_add_start)],
                states={
                    VC_SA_ADD_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, vc_sa_add_id)],
                    VC_SA_ADD_SCOPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, vc_sa_add_scope)],
                },
                fallbacks=[CommandHandler("cancel", cancel)],
            )

            async def vc_sa_remove_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                if not is_auth(update.effective_user.id):
                    await update.message.reply_text(f"{RD} Unauthorized.")
                    return
                if not ctx.args:
                    await update.message.reply_text(f"{RD} Usage: /vc_remove_subadmin <id>")
                    return
                try:
                    sub_id = int(ctx.args[0])
                except ValueError:
                    await update.message.reply_text(f"{RD} Invalid ID.")
                    return
                d = _db()
                try:
                    d.remove_vcounter_sub_admin(sub_id)
                finally:
                    d.close()
                await update.message.reply_text(f"{BG} VCounter sub-admin {sub_id} removed.")

            VC_PA_ADD_ID, VC_PA_ADD_SCOPE = range(8, 10)

            async def vc_pa_add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                if not is_auth(update.effective_user.id):
                    await update.message.reply_text(f"{RD} Unauthorized.")
                    return ConversationHandler.END
                await update.message.reply_text(f"{BL} Send vcounter sub-admin's Telegram ID:")
                return VC_PA_ADD_ID

            async def vc_pa_add_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                try:
                    sub_id = int(update.message.text.strip())
                except ValueError:
                    await update.message.reply_text(f"{RD} Invalid. Send a number:")
                    return VC_PA_ADD_ID
                ctx.user_data["vc_pa_sub_id"] = sub_id
                await update.message.reply_text(f"{BL} Send panel admin usernames to ADD (comma separated):")
                return VC_PA_ADD_SCOPE

            async def vc_pa_add_scope(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                new_admins = [a.strip() for a in update.message.text.split(",") if a.strip()]
                if not new_admins:
                    await update.message.reply_text(f"{RD} No admins. Try again:")
                    return VC_PA_ADD_SCOPE
                sub_id = ctx.user_data["vc_pa_sub_id"]
                d = _db()
                try:
                    sa = d.get_vcounter_sub_admin(sub_id)
                    if not sa:
                        await update.message.reply_text(f"{RD} Sub-admin {sub_id} not found.")
                        return ConversationHandler.END
                    current = json.loads(sa.get("allowed_admins", "[]"))
                    merged = list(dict.fromkeys(current + new_admins))
                    d.update_vcounter_sub_admin_scope(sub_id, merged)
                finally:
                    d.close()
                await update.message.reply_text(f"{BG} Updated.\nCan view: {', '.join(merged)}")
                return ConversationHandler.END

            vc_pa_add_conv = ConversationHandler(
                entry_points=[CommandHandler("vc_add_panel_admin", vc_pa_add_start)],
                states={
                    VC_PA_ADD_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, vc_pa_add_id)],
                    VC_PA_ADD_SCOPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, vc_pa_add_scope)],
                },
                fallbacks=[CommandHandler("cancel", cancel)],
            )

            VC_PA_RM_ID, VC_PA_RM_SCOPE = range(10, 12)

            async def vc_pa_rm_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                if not is_auth(update.effective_user.id):
                    await update.message.reply_text(f"{RD} Unauthorized.")
                    return ConversationHandler.END
                await update.message.reply_text(f"{BL} Send vcounter sub-admin's Telegram ID:")
                return VC_PA_RM_ID

            async def vc_pa_rm_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                try:
                    sub_id = int(update.message.text.strip())
                except ValueError:
                    await update.message.reply_text(f"{RD} Invalid. Send a number:")
                    return VC_PA_RM_ID
                ctx.user_data["vc_pa_rm_sub_id"] = sub_id
                await update.message.reply_text(f"{BL} Send panel admin usernames to REMOVE (comma separated):")
                return VC_PA_RM_SCOPE

            async def vc_pa_rm_scope(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                rm = [a.strip() for a in update.message.text.split(",") if a.strip()]
                if not rm:
                    await update.message.reply_text(f"{RD} No admins. Try again:")
                    return VC_PA_RM_SCOPE
                sub_id = ctx.user_data["vc_pa_rm_sub_id"]
                d = _db()
                try:
                    sa = d.get_vcounter_sub_admin(sub_id)
                    if not sa:
                        await update.message.reply_text(f"{RD} Sub-admin {sub_id} not found.")
                        return ConversationHandler.END
                    current = json.loads(sa.get("allowed_admins", "[]"))
                    remaining = [a for a in current if a not in rm]
                    d.update_vcounter_sub_admin_scope(sub_id, remaining)
                finally:
                    d.close()
                await update.message.reply_text(
                    f"{BG} Updated.\nCan view: {', '.join(remaining) if remaining else 'none'}"
                )
                return ConversationHandler.END

            vc_pa_rm_conv = ConversationHandler(
                entry_points=[CommandHandler("vc_remove_panel_admin", vc_pa_rm_start)],
                states={
                    VC_PA_RM_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, vc_pa_rm_id)],
                    VC_PA_RM_SCOPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, vc_pa_rm_scope)],
                },
                fallbacks=[CommandHandler("cancel", cancel)],
            )

            async def cb_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                q = update.callback_query
                await q.answer()
                uid = q.from_user.id
                data = q.data

                if data == "noop":
                    return

                if data == "menu_main":
                    if is_auth(uid):
                        name = q.from_user.first_name or "User"
                        text = (
                            f"{CY} MarzTool Bot{GY}\n"
                            f"{'='*28}\n\n"
                            f"Welcome {BG} {name}{GY}!\n"
                            f"Role: {BG} Main Admin\n\n"
                            f"Tap a button below:"
                        )
                        await q.edit_message_text(text, reply_markup=admin_menu_kb())
                    return

                if data == "menu_counter":
                    text = f"{CY} Counter Menu\n{'='*28}\n500MB threshold | 7-day gap\n\nChoose an option:"
                    await q.edit_message_text(text, reply_markup=counter_menu_kb())
                    return

                if data == "menu_daemon":
                    text = f"{BL} Daemon Control\n{'='*28}"
                    await q.edit_message_text(text, reply_markup=daemon_menu_kb())
                    return

                if data == "menu_ip":
                    text = f"{PK} IP Manager\n{'='*28}"
                    await q.edit_message_text(text, reply_markup=ip_menu_kb())
                    return

                if data == "menu_subadmin":
                    text = f"{GY} Sub-Admin Management\n{'='*28}"
                    await q.edit_message_text(text, reply_markup=subadmin_menu_kb())
                    return

                if data == "count_view":
                    d = _db()
                    try:
                        from modules.counter import Counter
                        counter = Counter(None, d)
                        viewer_key = f"tg_{uid}"
                        if is_auth(uid):
                            report = counter.get_report(viewer=viewer_key)
                        else:
                            scope = sub_scope(uid)
                            if scope:
                                report = counter.get_report(admin_username=scope[0], viewer=viewer_key)
                            else:
                                report = {"admins": [], "total": 0}
                        if not report["admins"]:
                            await q.edit_message_text(f"{GY} No counts yet.\n\nTap Back.", reply_markup=counter_menu_kb())
                            return
                        lines = [f"  {u['admin_username']}:  {u['total_count']}" for u in report["admins"]]
                        text = f"{CY} User Counts\n{'-'*28}\n" + "\n".join(lines) + f"\n{'-'*28}\n  Total: {report['total']}"
                        await q.edit_message_text(text, reply_markup=counter_menu_kb())
                    finally:
                        d.close()
                    return

                if data == "count_report":
                    d = _db()
                    try:
                        from modules.counter import Counter
                        counter = Counter(None, d)
                        viewer_key = f"tg_{uid}"
                        if is_auth(uid):
                            report = counter.get_report(viewer=viewer_key)
                        else:
                            scope = sub_scope(uid)
                            if scope:
                                report = counter.get_report(admin_username=scope[0], viewer=viewer_key)
                            else:
                                report = {"admins": [], "total": 0}
                        if not report["admins"]:
                            await q.edit_message_text(f"{GY} No data.\n\nTap Back.", reply_markup=counter_menu_kb())
                            return
                        lines = [f"  {u['admin_username']}:  {u['total_count']}" for u in report["admins"]]
                        text = f"{CY} === FULL REPORT ===\n\n" + "\n".join(lines) + f"\n\n  {BG}Grand Total: {report['total']}"
                        await q.edit_message_text(text, reply_markup=counter_menu_kb())
                    finally:
                        d.close()
                    return

                if data == "count_reset":
                    if not is_auth(uid):
                        await q.edit_message_text(f"{RD} Only main admin.", reply_markup=admin_menu_kb())
                        return
                    d = _db()
                    try:
                        d.reset_all_counters()
                    finally:
                        d.close()
                    await q.edit_message_text(f"{BG} All counters reset.", reply_markup=counter_menu_kb())
                    return

                if data == "count_settle":
                    d = _db()
                    try:
                        admin_name = None
                        viewer_key = f"tg_{uid}"
                        if is_auth(uid):
                            c = _cfg()
                            admin_name = c.get_username()
                            c.db.close()
                        elif is_sub(uid):
                            scope = sub_scope(uid)
                            if scope:
                                admin_name = scope[0]
                        if not admin_name:
                            await q.edit_message_text(f"{RD} Cannot determine admin.", reply_markup=counter_menu_kb())
                            return
                        from modules.counter import Counter
                        counter = Counter(None, d)
                        settled = counter.settle(admin_name, viewer_key)
                    finally:
                        d.close()
                    if settled <= 0:
                        await q.edit_message_text(f"{GY} Nothing to settle.", reply_markup=counter_menu_kb())
                    else:
                        await q.edit_message_text(
                            f"{BG} Counter settled.\nReset {settled} configs from your view.",
                            reply_markup=counter_menu_kb(),
                        )
                    return

                if data == "count_settlements":
                    d = _db()
                    try:
                        viewer_key = f"tg_{uid}"
                        settlements = d.get_counter_settlements()
                        if is_sub(uid):
                            settlements = [s for s in settlements if s["settled_by"] == viewer_key]
                        if not settlements:
                            await q.edit_message_text(f"{GY} No settlements.", reply_markup=counter_menu_kb())
                            return
                        lines = []
                        for s in settlements[:10]:
                            lines.append(f"  {s['admin_username']} settled by {s['settled_by']}: {s['amount_count']} configs\n  {s['settled_at'][:16]}")
                        text = f"{CY} Counter Settlements\n{'='*28}\n\n" + "\n\n".join(lines)
                        await q.edit_message_text(text, reply_markup=counter_menu_kb())
                    finally:
                        d.close()
                    return

                if data == "menu_vcounter":
                    text = (
                        f"{BL} VCounter Menu\n"
                        f"{'='*28}\n"
                        f"Track volume (GB) per admin\n\n"
                        f"Choose an option:"
                    )
                    await q.edit_message_text(text, reply_markup=vcounter_menu_kb())
                    return

                if data == "vc_view":
                    d = _db()
                    try:
                        from modules.vcounter import VCounter
                        vc = VCounter(None, d)
                        viewer_key = f"tg_{uid}"
                        if is_auth(uid):
                            report = vc.get_report(viewer=viewer_key)
                        elif is_sub(uid):
                            scope = sub_scope(uid)
                            if scope:
                                report = vc.get_report(admin_username=scope[0], viewer=viewer_key)
                            else:
                                report = {"admins": [], "total_bytes": 0}
                        else:
                            report = {"admins": [], "total_bytes": 0}
                        if not report["admins"]:
                            await q.edit_message_text(f"{GY} No volume data yet.\n\nTap Back.", reply_markup=vcounter_menu_kb())
                            return
                        GB = 1024 * 1024 * 1024
                        lines = [f"  {a['admin_username']}:  {a['total_volume_bytes'] / GB:.2f} GB" for a in report["admins"]]
                        total_gb = report["total_bytes"] / GB
                        text = (
                            f"{BL} Volume by Admin\n"
                            f"{'-'*28}\n"
                            + "\n".join(lines) +
                            f"\n{'-'*28}\n"
                            f"  Total: {total_gb:.2f} GB"
                        )
                        await q.edit_message_text(text, reply_markup=vcounter_menu_kb())
                    finally:
                        d.close()
                    return

                if data == "vc_report":
                    d = _db()
                    try:
                        from modules.vcounter import VCounter
                        vc = VCounter(None, d)
                        viewer_key = f"tg_{uid}"
                        if is_auth(uid):
                            report = vc.get_report(viewer=viewer_key)
                        elif is_sub(uid):
                            scope = sub_scope(uid)
                            if scope:
                                report = vc.get_report(admin_username=scope[0], viewer=viewer_key)
                            else:
                                report = {"admins": [], "total_bytes": 0}
                        else:
                            report = {"admins": [], "total_bytes": 0}
                        if not report["admins"]:
                            await q.edit_message_text(f"{GY} No data.\n\nTap Back.", reply_markup=vcounter_menu_kb())
                            return
                        GB = 1024 * 1024 * 1024
                        total_gb = report["total_bytes"] / GB
                        lines = [f"  {a['admin_username']}:  {a['total_volume_bytes'] / GB:.2f} GB" for a in report["admins"]]
                        text = (
                            f"{BL} === VCounter FULL REPORT ===\n\n"
                            + "\n".join(lines) +
                            f"\n\n  {BG}Grand Total: {total_gb:.2f} GB"
                        )
                        await q.edit_message_text(text, reply_markup=vcounter_menu_kb())
                    finally:
                        d.close()
                    return

                if data == "vc_settle":
                    d = _db()
                    try:
                        admin_name = None
                        viewer_key = f"tg_{uid}"
                        if is_auth(uid):
                            c = _cfg()
                            admin_name = c.get_username()
                            c.db.close()
                        elif is_sub(uid):
                            scope = sub_scope(uid)
                            if scope:
                                admin_name = scope[0]
                        if not admin_name:
                            await q.edit_message_text(f"{RD} Cannot determine admin.", reply_markup=vcounter_menu_kb())
                            return
                        from modules.vcounter import VCounter
                        vc = VCounter(None, d)
                        settled = vc.settle(admin_name, viewer_key)
                        GB = 1024 * 1024 * 1024
                    finally:
                        d.close()
                    if settled <= 0:
                        await q.edit_message_text(f"{GY} Nothing to settle.", reply_markup=vcounter_menu_kb())
                    else:
                        await q.edit_message_text(
                            f"{BG} VCounter settled.\nReset {settled / GB:.2f} GB from your view.",
                            reply_markup=vcounter_menu_kb(),
                        )
                    return

                if data == "vc_settlements":
                    d = _db()
                    try:
                        viewer_key = f"tg_{uid}"
                        settlements = d.get_vcounter_settlements()
                        if is_sub(uid):
                            settlements = [s for s in settlements if s["settled_by"] == viewer_key]
                        if not settlements:
                            await q.edit_message_text(f"{GY} No settlements.", reply_markup=vcounter_menu_kb())
                            return
                        GB = 1024 * 1024 * 1024
                        lines = []
                        for s in settlements[:10]:
                            lines.append(f"  {s['admin_username']} settled by {s['settled_by']}: {s['amount_bytes'] / GB:.2f} GB\n  {s['settled_at'][:16]}")
                        text = f"{BL} VCounter Settlements\n{'='*28}\n\n" + "\n\n".join(lines)
                        await q.edit_message_text(text, reply_markup=vcounter_menu_kb())
                    finally:
                        d.close()
                    return

                if data == "vc_reset":
                    if not is_auth(uid):
                        await q.edit_message_text(f"{RD} Only main admin.", reply_markup=admin_menu_kb())
                        return
                    d = _db()
                    try:
                        cursor = d.conn.cursor()
                        cursor.execute("DELETE FROM vcounter_totals")
                        d.conn.commit()
                    finally:
                        d.close()
                    await q.edit_message_text(f"{BG} All vcounters reset.", reply_markup=vcounter_menu_kb())
                    return

                if data == "daemon_logs":
                    from modules.daemon import LOG_FILE
                    if not LOG_FILE.exists():
                        await q.edit_message_text(f"{GY} No logs yet.", reply_markup=daemon_menu_kb())
                        return
                    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()[-15:]
                    text = f"{CY} Logs\n{'-'*28}\n" + "".join(lines)
                    if len(text) > 3900:
                        text = text[-3900:]
                    await q.message.reply_text(text or f"{GY} Empty.")
                    return

                if data == "ip_users":
                    d = _db()
                    try:
                        tracked = d.get_all_tracked_users()
                        if not tracked:
                            await q.edit_message_text(f"{GY} No tracked users.", reply_markup=ip_menu_kb())
                            return
                        lines = [f"  {t['email']}:  {len(t['ips'])} IPs" for t in tracked[:20]]
                        text = f"{PK} Tracked Users\n{'-'*28}\n" + "\n".join(lines)
                        await q.edit_message_text(text, reply_markup=ip_menu_kb())
                    finally:
                        d.close()
                    return

                if data == "ip_banned":
                    bp = Path(__file__).parent.parent / "blocked_ips.csv"
                    if not bp.exists():
                        await q.edit_message_text(f"{GY} No banned IPs.", reply_markup=ip_menu_kb())
                        return
                    content = bp.read_text().strip()
                    if not content:
                        await q.edit_message_text(f"{GY} No banned IPs.", reply_markup=ip_menu_kb())
                        return
                    ips = [l.split(",")[0] for l in content.split("\n") if l.strip()]
                    text = f"{RD} Banned IPs\n{'-'*28}\n" + "\n".join(f"  {ip}" for ip in ips[:20])
                    await q.edit_message_text(text, reply_markup=ip_menu_kb())
                    return

                if data == "ip_unban":
                    import subprocess
                    try:
                        subprocess.run(["iptables", "-F"], capture_output=True, timeout=10)
                        bp = Path(__file__).parent.parent / "blocked_ips.csv"
                        bp.write_text("")
                        await q.edit_message_text(f"{BG} All IPs unbanned.", reply_markup=ip_menu_kb())
                    except Exception as e:
                        await q.edit_message_text(f"{RD} Error: {e}", reply_markup=ip_menu_kb())
                    return

                if data == "sa_list":
                    d = _db()
                    try:
                        subs = d.get_all_sub_admins()
                        if not subs:
                            await q.edit_message_text(f"{GY} No sub-admins.", reply_markup=subadmin_menu_kb())
                            return
                        lines = []
                        for s in subs:
                            allowed = json.loads(s.get("allowed_admins", "[]"))
                            lines.append(f"  ID: {s['telegram_id']}\n  View: {', '.join(allowed)}")
                        text = f"{BL} Sub-Admins\n{'='*28}\n\n" + "\n\n".join(lines)
                        await q.edit_message_text(text, reply_markup=subadmin_menu_kb())
                    finally:
                        d.close()
                    return

                if data in ("sa_add", "sa_remove", "sa_add_panel", "sa_rm_panel"):
                    if not is_auth(uid):
                        await q.edit_message_text(f"{RD} Only main admin.", reply_markup=subadmin_menu_kb())
                        return
                    cmds = {
                        "sa_add": "/add_subadmin",
                        "sa_remove": "/remove_subadmin <id>",
                        "sa_add_panel": "/add_panel_admin",
                        "sa_rm_panel": "/remove_panel_admin",
                    }
                    await q.edit_message_text(f"{BL} Use: {cmds[data]}", reply_markup=subadmin_menu_kb())
                    return

                if data == "vc_sa_list":
                    d = _db()
                    try:
                        subs = d.get_all_vcounter_sub_admins()
                        if not subs:
                            await q.edit_message_text(f"{GY} No vcounter sub-admins.", reply_markup=subadmin_menu_kb())
                            return
                        lines = []
                        for s in subs:
                            allowed = json.loads(s.get("allowed_admins", "[]"))
                            lines.append(f"  ID: {s['telegram_id']}\n  View: {', '.join(allowed)}")
                        text = f"{BL} VCounter Sub-Admins\n{'='*28}\n\n" + "\n\n".join(lines)
                        await q.edit_message_text(text, reply_markup=subadmin_menu_kb())
                    finally:
                        d.close()
                    return

                if data in ("vc_sa_add", "vc_sa_remove", "vc_sa_add_panel", "vc_sa_rm_panel"):
                    if not is_auth(uid):
                        await q.edit_message_text(f"{RD} Only main admin.", reply_markup=subadmin_menu_kb())
                        return
                    cmds = {
                        "vc_sa_add": "/vc_add_subadmin",
                        "vc_sa_remove": "/vc_remove_subadmin <id>",
                        "vc_sa_add_panel": "/vc_add_panel_admin",
                        "vc_sa_rm_panel": "/vc_remove_panel_admin",
                    }
                    await q.edit_message_text(f"{BL} Use: {cmds[data]}", reply_markup=subadmin_menu_kb())
                    return

                if data.startswith("vl_exempt:"):
                    if not is_auth(uid):
                        await q.answer("Only main admin.", show_alert=True)
                        return
                    parts = data.split(":")
                    if len(parts) != 3:
                        return
                    target_username = parts[1]
                    try:
                        notif_id = int(parts[2])
                    except ValueError:
                        return
                    d = _db()
                    try:
                        from datetime import datetime, timezone
                        d.add_exempt(target_username, datetime.now(timezone.utc).isoformat())
                    finally:
                        d.close()
                    old_text = q.message.text or ""
                    new_text = old_text + f"\n\n{BG} EXEMPTED — will not be limited"
                    try:
                        await q.edit_message_text(new_text, reply_markup=None)
                    except Exception:
                        pass
                    await q.answer(f"{target_username} exempted from volume limit", show_alert=True)
                    return

                if data == "menu_volume":
                    d = _db()
                    try:
                        exempt = d.get_all_exempt_users()
                    finally:
                        d.close()
                    vl_gb = _cfg().get_volume_limit_gb()
                    vl_on = _cfg().get_volume_limit_enabled()
                    vl_status = f"{BG} ON ({vl_gb}GB)" if vl_on else f"{RD} OFF"
                    kb = [
                        [InlineKeyboardButton(f"Status: {vl_status}", callback_data="noop")],
                        [InlineKeyboardButton("View Exempt List", callback_data="vl_list")],
                        [InlineKeyboardButton("Add Exempt", callback_data="vl_add")],
                        [InlineKeyboardButton("Remove Exempt", callback_data="vl_rm")],
                        [InlineKeyboardButton("Back", callback_data="menu_main")],
                    ]
                    text = f"{BM} Volume Limit\n{'='*28}\nLimit: {vl_gb} GB per user"
                    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                    return

                if data == "vl_list":
                    if not is_auth(uid):
                        await q.answer("Only main admin.", show_alert=True)
                        return
                    d = _db()
                    try:
                        exempt = d.get_all_exempt_users()
                    finally:
                        d.close()
                    if not exempt:
                        text = f"{GY} No exempt users."
                    else:
                        lines = [f"  {e['username']}" for e in exempt[:20]]
                        text = f"{BL} Exempt Users\n{'-'*28}\n" + "\n".join(lines)
                    kb = [
                        [InlineKeyboardButton("Back", callback_data="menu_volume")]
                    ]
                    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                    return

                if data == "vl_add":
                    if not is_auth(uid):
                        await q.answer("Only main admin.", show_alert=True)
                        return
                    await q.edit_message_text(
                        f"{BL} Send the username to exempt:"
                    )
                    ctx.user_data["vl_add"] = True
                    return

                if data == "vl_rm":
                    if not is_auth(uid):
                        await q.answer("Only main admin.", show_alert=True)
                        return
                    await q.edit_message_text(
                        f"{BL} Send the username to remove from exempt:"
                    )
                    ctx.user_data["vl_rm"] = True
                    return

            app = ApplicationBuilder().token(token).build()
            self.app = app

            async def exempt_text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
                uid = update.effective_user.id
                if not is_auth(uid):
                    return
                text = (update.message.text or "").strip()
                if ctx.user_data.get("vl_add"):
                    ctx.user_data.pop("vl_add", None)
                    if not text:
                        await update.message.reply_text(f"{RD} No username provided.")
                        return
                    d = _db()
                    try:
                        from datetime import datetime, timezone
                        d.add_exempt(text, datetime.now(timezone.utc).isoformat())
                    finally:
                        d.close()
                    kb = [[InlineKeyboardButton("Back", callback_data="menu_volume")]]
                    await update.message.reply_text(
                        f"{BG} {text} added to exempt list.",
                        reply_markup=InlineKeyboardMarkup(kb),
                    )
                    return
                if ctx.user_data.get("vl_rm"):
                    ctx.user_data.pop("vl_rm", None)
                    if not text:
                        await update.message.reply_text(f"{RD} No username provided.")
                        return
                    d = _db()
                    try:
                        d.remove_exempt(text)
                    finally:
                        d.close()
                    kb = [[InlineKeyboardButton("Back", callback_data="menu_volume")]]
                    await update.message.reply_text(
                        f"{BG} {text} removed from exempt list.",
                        reply_markup=InlineKeyboardMarkup(kb),
                    )
                    return

            app.add_handler(CommandHandler("start", start_cmd))
            app.add_handler(CommandHandler("count", count_cmd))
            app.add_handler(CommandHandler("report", report_cmd))
            app.add_handler(CommandHandler("status", status_cmd))
            app.add_handler(CommandHandler("logs", logs_cmd))
            app.add_handler(CommandHandler("users", users_cmd))
            app.add_handler(CommandHandler("ban_list", ban_list_cmd))
            app.add_handler(CommandHandler("unban_all", unban_all_cmd))
            app.add_handler(CommandHandler("count_reset", count_reset_cmd))
            app.add_handler(CommandHandler("remove_subadmin", sa_remove_cmd))
            app.add_handler(CommandHandler("list_subadmins", sa_list_cmd))
            app.add_handler(sa_add_conv)
            app.add_handler(pa_add_conv)
            app.add_handler(pa_rm_conv)
            app.add_handler(CommandHandler("vc_list_subadmins", vc_sa_list_cmd))
            app.add_handler(CommandHandler("vc_remove_subadmin", vc_sa_remove_cmd))
            app.add_handler(vc_sa_add_conv)
            app.add_handler(vc_pa_add_conv)
            app.add_handler(vc_pa_rm_conv)
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, exempt_text_handler))
            app.add_handler(CallbackQueryHandler(cb_handler))

            async def _run_async():
                await app.initialize()
                await app.start()
                await app.updater.start_polling(drop_pending_updates=True)
                self.log.info("Telegram bot polling is ACTIVE")
                stop_event = asyncio.Event()
                await stop_event.wait()

            def _run():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                try:
                    self._loop.run_until_complete(_run_async())
                except Exception as e:
                    self.log.error("Telegram bot crashed: %s", e)

            self._thread = threading.Thread(target=_run, daemon=True, name="tg-bot")
            self._thread.start()

            import time as _t
            _t.sleep(1)
            self.log.info("Telegram bot thread started")
            return True

        except Exception as e:
            self.log.error("Failed to start telegram bot: %s", e)
            return False

    def stop(self):
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self.app = None
        self._thread = None
        self._loop = None

    def test_connection(self) -> tuple[bool, str]:
        token = self.config.get_telegram_token()
        admin_id = self.config.get_telegram_admin_id()
        if not token or not admin_id:
            return False, "Token or admin ID not configured"

        try:
            import requests
            r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
            data = r.json()
            if not data.get("ok"):
                return False, f"API error: {data.get('description', 'unknown')}"
            bot_name = data["result"].get("username", "?")

            r2 = requests.get(
                f"https://api.telegram.org/bot{token}/getChat",
                params={"chat_id": int(admin_id)},
                timeout=10,
            )
            d2 = r2.json()
            if not d2.get("ok"):
                return False, f"Admin chat error: {d2.get('description', 'unknown')}"

            r3 = requests.get(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": int(admin_id), "text": "MarzTool test OK"},
                timeout=10,
            )
            d3 = r3.json()
            if not d3.get("ok"):
                return False, f"Send failed: {d3.get('description', 'unknown')}"

            return True, f"Bot: @{bot_name} | Test message sent OK"
        except requests.exceptions.ConnectionError:
            return False, "Cannot reach api.telegram.org"
        except requests.exceptions.Timeout:
            return False, "Connection timed out"
        except Exception as e:
            return False, f"Error: {e}"

    def send_message(self, text: str):
        token = self.config.get_telegram_token()
        admin_id = self.config.get_telegram_admin_id()
        if not token or not admin_id:
            return
        try:
            import requests
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": int(admin_id), "text": text},
                timeout=10,
            )
        except Exception as e:
            self.log.error("Failed to send telegram message: %s", e)
