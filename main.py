import re
import time
import vk_api
import random
import argparse

import chat_manager
import message_parser

from vk_api.longpoll import VkLongPoll, VkEventType, Event

from threading import Thread

pin_code = random.randint(10000, 999999)
message_parser = message_parser.MessageParser(command_symbol=':')
vk = None
running = False
parsed_args = {}


def new_post(post):
    sub_type = 'group' if post['source_id'] < 0 else 'user'
    id = abs(post['source_id'])

    for peer in chat_manager.get_peers(sub_type, id):
        vk.messages.send(peer_id=peer, attachment='wall{0}_{1}'.format(post['source_id'], post['post_id']))


def read_feed():
    last_check = time.time()

    while running:
        items = vk.newsfeed.get(start_time=int(last_check))["items"]

        for item in items:
            new_post(item)

        last_check = time.time()
        time.sleep(parsed_args.wait)


def pincode_command(event: Event, pin: str):
    global pin_code

    old_pin_code = pin_code
    pin_code = random.randint(10000, 999999)
    print('New pin-code: {0}'.format(pin_code))

    if pin == str(old_pin_code):
        response = vk.users.get(user_ids=event.user_id, fields=['first_name', 'last_name'])[0]
        username = '{first_name} {last_name}'.format(**response)

        chat_manager.add_admin(event.user_id)

        return '*{0} ({1}) was promoted.\nPin-code changed.'.format(event.user_id, username)
    else:
        return 'Pin-code mismatched.\nPin-code changed.'


def check_permission(event: Event):
    if event.from_user:
        return True
    elif event.from_chat and vk.messages.getChat(chat_id=event.chat_id)['admin_id'] == event.user_id:
        return True
    else:
        return chat_manager.is_admin(event.chat_id, event.user_id)


def list_subscriptions(event: Event, *args):
    subscriptions = chat_manager.get_subscriptions(event.peer_id)

    if subscriptions.count() == 0:
        return 'You are not subscribed for anything.'

    message = 'Your subscriptions:\n'

    for subscription in subscriptions:
        sid = subscription[subscription['type']]
        if subscription['type'] == 'group':
            group = vk.groups.getById(group_id=sid)[0]
            name = group['name']
            screen_name = group['screen_name']
        elif subscription['type'] == 'user':
            user = vk.users.get(user_ids=sid, fields='screen_name')[0]
            name = user['first_name'] + ' ' + user['last_name']
            screen_name = user['screen_name']
        else:
            continue

        message += '{0} (https://vk.com/{1})\n\n'.format(name, screen_name)

    return message


def subscribe_group(event: Event, link: str, *args):
    if not check_permission(event):
        return 'You are not admin.'

    try:
        group_id = link.split('com/')[1]
        resp = vk.groups.getById(group_id=group_id)

        if 'error' in resp:
            return 'Could not find group with id {0}'.format(group_id)
        group_name = resp[0]['name']

        if chat_manager.is_subscribed('group', event.peer_id, resp[0]["id"]):
            return 'Already subscribed for {0}'.format(group_name)

        vk.groups.join(group_id=resp[0]['id'])

        chat_manager.subscribe_group(event.peer_id, resp[0]["id"])

        return 'Subscribed for {0}'.format(group_name)
    except:
        return 'Could not subscribe'


def unsubscribe_group(event: Event, link: str):
    if not check_permission(event):
        return 'You are not admin.'

    try:
        group_id = link.split('com/')[1]
        resp = vk.groups.getById(group_id=group_id)

        if 'error' in resp:
            return 'Could not find group with id {0}'.format(group_id)
        group_name = resp[0]['name']

        if not chat_manager.is_subscribed('group', event.peer_id, resp[0]["id"]):
            return 'You are not subscribed for {0}'.format(group_name)

        chat_manager.unsubscribe_group(event.peer_id, resp[0]["id"])

        return 'Unsubscribed from {0}'.format(group_name)
    except:
        return 'Could not unsubscribe'


def subscribe_user(event: Event, link: str, filter: str = '', *args):
    if not check_permission(event):
        return 'You are not admin.'

    try:
        user_id = link.split('com/')[1]
        resp = vk.users.get(user_ids=user_id)

        if 'error' in resp:
            return 'Could not find user with id {0}'.format(user_id)
        user_name = '{first_name} {last_name}'.format(**resp[0])

        if chat_manager.is_subscribed('user', event.peer_id, resp[0]["id"]):
            return 'Already subscribed for {0}'.format(user_name)

        if vk.friends.areFriends(user_ids=resp[0]["id"])[0]["friend_status"] == 0:
            vk.friends.add(user_id=resp[0]["id"], text='Здравствуйте, я автоматический бот для агрегации собщений '
                                                       'преподавателей. Я подписался на вас, что бы пересылать ваши '
                                                       'посты в группы ИПМ\'а. Не обязательно добавлять меня в '
                                                       'друзья. Автор - @yegorf1')

        chat_manager.subscribe_user(event.peer_id, resp[0]["id"], filter)

        return 'Subscribed for {0}'.format(user_name)
    except:
        return 'Unable to subscribe'


def unsubscribe_user(event: Event, link: str, filter: str = '', *args):
    if not check_permission(event):
        return 'You are not admin.'

    try:
        user_id = link.split('com/')[1]
        resp = vk.users.get(user_ids=user_id)

        if 'error' in resp:
            return 'Could not find user with id {0}'.format(user_id)
        user_name = '{first_name} {last_name}'.format(**resp[0])

        if not chat_manager.is_subscribed('user', event.peer_id, resp[0]["id"]):
            return 'Not subscribed for {0}'.format(user_name)

        chat_manager.unsubscribe_user(event.peer_id, resp[0]["id"])

        return 'Unsubscribed from {0}'.format(user_name)
    except Exception as e:
        return 'Unable to unsubscribe'


def new_message(event: Event):
    if event.from_me:
        return

    if event.from_group:
        return

    answer = None
    try:
        res = message_parser.parse(event.text)
        if res is not None:
            action, args = res
            answer = action(event, *args)
    except ValueError as e:
        answer = 'Error at parsing: {0}'.format(e)
    except Exception as e:
        answer = str(e)

    if answer is None:
        return

    vk.messages.send(peer_id=event.peer_id, message=answer)


def main(login, password):
    print('Admin pin code: {0}'.format(pin_code))

    vk_session = vk_api.VkApi(login, password)

    vk_session.auth()
    global vk
    vk = vk_session.get_api()

    longpoll = VkLongPoll(vk_session)

    global running
    try:
        running = True

        news_thread = Thread(target=read_feed)
        news_thread.start()

        for event in longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW:
                new_message(event)
    except InterruptedError:
        running = False


if __name__ == '__main__':
    args_parser = argparse.ArgumentParser(description='Re-sends all information from ITMO teachers to student groups.')
    args_parser.add_argument('--login', '-l', type=str, dest='login', required=True, help='VK login')
    args_parser.add_argument('--password', '-p', type=str, dest='password', required=True, help='VK password')
    args_parser.add_argument('--wait', '-w', type=float, dest='wait', help='Time to wait between news checks',
                             default=3)

    parsed_args = args_parser.parse_args()

    message_parser.add_command('pincode',
                               action=pincode_command,
                               help_message='Activates admin privileges by pincode',
                               args_description='pincode')

    message_parser.add_command('list',
                               action=list_subscriptions,
                               help_message='Lists all subscriptions')

    message_parser.add_command('subscribe_group',
                               action=subscribe_group,
                               help_message='Subscribe group for current chat for notifications',
                               args_description='link_to_group')

    message_parser.add_command('unsubscribe_group',
                               action=unsubscribe_group,
                               help_message='Unsubscribes chat from post of group',
                               args_description='link_to_user')

    message_parser.add_command('subscribe_user',
                               action=subscribe_user,
                               help_message='Connect user posts to current chat',
                               args_description='link_to_user')

    message_parser.add_command('unsubscribe_user',
                               action=unsubscribe_user,
                               help_message='Unsubscribes chat from post of user',
                               args_description='link_to_user')

    main(parsed_args.login, parsed_args.password)
