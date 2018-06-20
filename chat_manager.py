from pymongo import MongoClient

client = MongoClient()
database = client['vk_notifications']


def add_admin(userid):
    database.admins.insert_one({'userid': userid})


def get_admins():
    return database.admins.distinct('userid')


def is_subscribed(subscription_type: str, peer: str, id: str):
    count = database.subscriptions.count({'peer': peer, 'type': subscription_type, subscription_type: id})
    return count > 0


def subscribe_group(peer_id, group_id):
    database.subscriptions.insert_one({'peer': peer_id, 'type': 'group', 'group': group_id})


def is_admin(chat_id, user_id):
    return user_id in get_admins()


def get_peers(subscription_type, id):
    return database.subscriptions.distinct('peer', {'type': subscription_type, subscription_type: id})


def get_subscriptions(peer_id):
    return database.subscriptions.find({'peer': peer_id})


def subscribe_user(peer_id, user_id, filter=None):
    database.subscriptions.insert_one({'peer': peer_id, 'type': 'user', 'user': user_id, 'filter': filter})


def unsubscribe_group(peer_id, id):
    database.subscriptions.remove({'peer': peer_id, 'type': 'group', 'group': id})


def unsubscribe_user(peer_id, id):
    database.subscriptions.remove({'peer': peer_id, 'type': 'user', 'user': id})
