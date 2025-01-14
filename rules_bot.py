import configparser
import logging
import os

from telegram import (
    ParseMode,
    Bot,
    Update,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeAllGroupChats,
)
from telegram.error import BadRequest, Unauthorized
from telegram.ext import (
    CommandHandler,
    Updater,
    MessageHandler,
    Filters,
    Defaults,
    ChatMemberHandler,
)

from components import inlinequeries, taghints
from components.callbacks import (
    start,
    rules,
    docs,
    wiki,
    help_callback,
    off_on_topic,
    sandwich,
    github,
    delete_new_chat_members_message,
    greet_new_chat_members,
)
from components.errorhandler import error_handler
from components.const import (
    OFFTOPIC_RULES,
    OFFTOPIC_USERNAME,
    ONTOPIC_RULES,
    ONTOPIC_USERNAME,
    ONTOPIC_RULES_MESSAGE_ID,
    OFFTOPIC_RULES_MESSAGE_ID,
    ONTOPIC_CHAT_ID,
    OFFTOPIC_CHAT_ID,
)
from components.util import (
    rate_limit_tracker,
)
from components.github import github_issues

if os.environ.get('ROOLSBOT_DEBUG'):
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG
    )
else:
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
    )
    logging.getLogger('apscheduler').setLevel(logging.WARNING)
    logging.getLogger('github3').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def update_rules_messages(bot: Bot) -> None:
    try:
        bot.edit_message_text(
            chat_id=ONTOPIC_CHAT_ID,
            message_id=ONTOPIC_RULES_MESSAGE_ID,
            text=ONTOPIC_RULES,
        )
    except (BadRequest, Unauthorized) as exc:
        logger.warning('Updating on-topic rules failed: %s', exc)
    try:
        bot.edit_message_text(
            chat_id=OFFTOPIC_CHAT_ID,
            message_id=OFFTOPIC_RULES_MESSAGE_ID,
            text=OFFTOPIC_RULES,
        )
    except (BadRequest, Unauthorized) as exc:
        logger.warning('Updating off-topic rules failed: %s', exc)


def main() -> None:
    config = configparser.ConfigParser()
    config.read('bot.ini')

    defaults = Defaults(parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    updater = Updater(token=config['KEYS']['bot_api'], defaults=defaults)
    dispatcher = updater.dispatcher
    update_rules_messages(updater.bot)

    dispatcher.add_handler(MessageHandler(~Filters.command, rate_limit_tracker), group=-1)

    # Note: Order matters!
    # Taghints - works with regex
    taghints.register(dispatcher)

    # Simple commands
    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('rules', rules))
    dispatcher.add_handler(MessageHandler(Filters.regex(r'.*#rules.*'), rules))
    dispatcher.add_handler(CommandHandler('docs', docs))
    dispatcher.add_handler(CommandHandler('wiki', wiki))
    dispatcher.add_handler(CommandHandler('help', help_callback))

    # Stuff that runs on every message with regex
    dispatcher.add_handler(
        MessageHandler(
            Filters.regex(r'(?i)[\s\S]*?((sudo )?make me a sandwich)[\s\S]*?'), sandwich
        )
    )
    dispatcher.add_handler(
        MessageHandler(
            Filters.regex(r'(?i)[\s\S]*?\b(?<!["\\])(off|on)[- _]?topic\b'), off_on_topic
        )
    )
    # We need several matches so Filters.regex is basically useless
    # therefore we catch everything and do regex ourselves
    # This should probably be in another dispatcher group
    # but I kept getting SystemErrors..
    dispatcher.add_handler(
        MessageHandler(Filters.text & Filters.update.messages & ~Filters.command, github)
    )

    # Status updates
    dispatcher.add_handler(
        ChatMemberHandler(greet_new_chat_members, chat_member_types=ChatMemberHandler.CHAT_MEMBER)
    )
    dispatcher.add_handler(
        MessageHandler(
            Filters.chat(username=[ONTOPIC_USERNAME, OFFTOPIC_USERNAME])
            & Filters.status_update.new_chat_members,
            delete_new_chat_members_message,
        ),
        group=1,
    )

    # Inline Queries
    inlinequeries.register(dispatcher)

    # Error Handler
    dispatcher.add_error_handler(error_handler)

    updater.start_polling(allowed_updates=Update.ALL_TYPES)
    logger.info('Listening...')

    try:
        github_issues.set_auth(
            config['KEYS']['github_client_id'], config['KEYS']['github_client_secret']
        )
    except KeyError:
        logging.info('No github api token set. Rate-limit is 60 requests/hour without auth.')

    github_issues.init_ptb_contribs(dispatcher.job_queue)  # type: ignore[arg-type]
    github_issues.init_issues(dispatcher.job_queue)  # type: ignore[arg-type]

    # set commands
    updater.bot.set_my_commands(
        [
            ('docs', 'Send the link to the docs.'),
            ('wiki', 'Send the link to the wiki.'),
            ('help', 'Send the link to this bots README.'),
            ('hints', 'List available tag hints.'),
        ],
        scope=BotCommandScopeAllPrivateChats(),
    )
    updater.bot.set_my_commands(
        [
            ('docs', 'Send the link to the docs.'),
            ('wiki', 'Send the link to the wiki.'),
            ('help', 'Send the link to this bots README.'),
        ],
        scope=BotCommandScopeAllGroupChats(),
    )
    for group_name in [ONTOPIC_CHAT_ID, OFFTOPIC_CHAT_ID]:
        updater.bot.set_my_commands(
            [
                ('docs', 'Send the link to the docs.'),
                ('wiki', 'Send the link to the wiki.'),
                ('rules', 'Show the rules for this group.'),
                ('help', 'Send the link to this bots README.'),
            ],
            scope=BotCommandScopeChat(group_name),
        )

    updater.idle()


if __name__ == '__main__':
    main()
