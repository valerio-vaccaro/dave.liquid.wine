#  dP oo                   oo       dP               oo
#  88                               88
#  88 dP .d8888b. dP    dP dP .d888b88    dP  dP  dP dP 88d888b. .d8888b.
#  88 88 88'  `88 88    88 88 88'  `88    88  88  88 88 88'  `88 88ooood8
#  88 88 88.  .88 88.  .88 88 88.  .88 dP 88.88b.88' 88 88    88 88.  ...
#  dP dP `8888P88 `88888P' dP `88888P8 88 8888P Y8P  dP dP    dP `88888P'
#              88
#              dP
#
#    MIT License - Valerio Vaccaro 2020
#    Based on open source code

from flask import Flask, request, send_from_directory, redirect, url_for
from flask_stache import render_template
from flask_qrcode import QRcode
from flask_socketio import SocketIO
from bitcoin_rpc_class import RPCHost
import os
import configparser
import mysql.connector
import json
import requests
import string
import random
import secrets
import wallycore as wally
from flask import jsonify
from flask import session

import numpy as np
import pandas as pd
from plotnine import *

app = Flask(__name__, static_url_path='/static')
qrcode = QRcode(app)

socketio = SocketIO(app)

config = configparser.RawConfigParser()
config.read('liquid.conf')

secToken = config.get('SECURITY', 'token')
secUuid = config.get('SECURITY', 'uuid')
adminUsername = config.get('ADMIN', 'username')
adminPassword = config.get('ADMIN', 'password')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form['username'] != adminUsername or request.form['password'] != adminPassword:
            error = 'Invalid Credentials. Please try again.'
        else:
            session['logged_in'] = True
            return redirect(url_for('utxos'))
    return render_template('login', error=error)

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session['logged_in'] = False
    return redirect(url_for('utxos'))

@app.route('/')
def home():
    tokens = []
    token = requests.get('https://amp-beta.blockstream.com/api/assets/{}'.format(secUuid), \
        headers={'content-type': 'application/json', 'Authorization': 'token {}'.format(secToken)}).json()
    tokens.append(token)

    logged = False
    if 'logged_in' in session:
        logged = session['logged_in']

    data = {
        'tokens': tokens,
        'logged': logged,
    }
    return render_template('home', **data)


@app.route('/utxos')
def utxos():
    command = request.args.get('command')
    txid = request.args.get('txid')
    vout = request.args.get('vout')

    if command is not None:
        if command=='lock' and txid is not None and vout is not None:
            res = requests.post('https://amp-beta.blockstream.com/api/assets/{}/utxos/blacklist'.format(secUuid), \
                headers={'content-type': 'application/json', 'Authorization': 'token {}'.format(secToken)}, \
                data=json.dumps([{'txid': txid, 'vout': int(vout)}])).json()

        if command=='unlock' and txid is not None and vout is not None:
            res = requests.post('https://amp-beta.blockstream.com/api/assets/{}/utxos/whitelist'.format(secUuid), \
                headers={'content-type': 'application/json', 'Authorization': 'token {}'.format(secToken)}, \
                data=json.dumps([{'txid': txid, 'vout': int(vout)}])).json()

    utxos = requests.get('https://amp-beta.blockstream.com/api/assets/{}/utxos'.format(secUuid), \
        headers={'content-type': 'application/json', 'Authorization': 'token {}'.format(secToken)}).json()

    logged = False
    if 'logged_in' in session:
        logged = session['logged_in']

    data = {
        'utxos': utxos,
        'logged': logged,
    }
    return render_template('utxos', **data)


@app.route('/stats')
def stats():
    os.system('python flowchart.py -u "https://amp-beta.blockstream.com" -t "{}" -a "{}" -f "flowchart"'.format(secToken, secUuid))
    os.system('mv flowchart.gv.png static/flowchart.png')
    os.system('rm flowchart.gv')

    activities = requests.get('https://amp-beta.blockstream.com/api/assets/{}/activities'.format(secUuid), \
        headers={'content-type': 'application/json', 'Authorization': 'token {}'.format(secToken)}).json()

    random_list = [random.choice(string.ascii_letters + string.digits) for n in range(32)]
    random_str = "".join(random_list)

    logged = False
    if 'logged_in' in session:
        logged = session['logged_in']

    data = {
        'random': random_str,
        'activities': activities,
        'logged': logged,
    }
    return render_template('stats', **data)


@app.route('/balance')
def balance():
    confirmed_balance = requests.get('https://amp-beta.blockstream.com/api/assets/{}/balance'.format(secUuid), \
        headers={'content-type': 'application/json', 'Authorization': 'token {}'.format(secToken)}).json()['confirmed_balance']

    # convert to pandas dataframe
    data = np.array([(e['GAID'], e['owner'], e['amount']) for e in confirmed_balance])
    df = pd.DataFrame({'gaid': data[:, 0], 'owner': data[:, 1], 'amount': data[:, 2]})
    df.replace(to_replace=[None], value=np.nan, inplace=True)

    # plot distribution
    plt1 = ggplot(df, aes(x='gaid', y='amount', fill='gaid')) + \
        geom_col() +   \
        coord_flip() + \
        scale_fill_brewer(type='div', palette="Spectral") + \
        labs(title ='Balance', x = 'GAID', y = 'Tokens')

    ggsave(filename="static/gaid_balance.png", plot=plt1, device='png', dpi=300)

    random_list = [random.choice(string.ascii_letters + string.digits) for n in range(32)]
    random_str = "".join(random_list)

    logged = False
    if 'logged_in' in session:
        logged = session['logged_in']

    data = {
        'random': random_str,
        'confirmed_balance': confirmed_balance,
        'logged': logged,
    }
    return render_template('balance', **data)


@app.route('/about')
def about():
    logged = False
    if 'logged_in' in session:
        logged = session['logged_in']

    data = {
        'logged': logged,
    }
    return render_template('about', **data)


@app.route('/investor', methods=['GET', 'POST'])
def investor():
    form = True
    status = ''

    if request.method == 'POST':
        form = False
        if request.form['command']  == 'investor':
            status = requests.post('https://amp-beta.blockstream.com/api/registered_users/add', \
                headers={'content-type': 'application/json', 'Authorization': 'token {}'.format(secToken)}, \
                data=json.dumps({'name': request.form['name'], 'GAID': request.form['gaid'], 'is_company': False})).json()

        elif request.form['command']  == 'assignment':
            status = requests.post('https://amp-beta.blockstream.com/api/assets/{}/assignments/create'.format(secUuid), \
                headers={'content-type': 'application/json', 'Authorization': 'token {}'.format(secToken)}, \
                data=json.dumps({"assignments": [{"registered_user": int(request.form['id']), "amount": int(request.form['amount']), "ready_for_distribution": True, "vesting_timestamp": None}]})).json()

    else:
        command = request.args.get('command')
        id = request.args.get('id')
        if command == 'add':
            status = requests.put('https://amp-beta.blockstream.com/api/categories/23/registered_users/{}/add'.format(id), \
                headers={'content-type': 'application/json', 'Authorization': 'token {}'.format(secToken)}).json()
        elif command == 'remove':
            status = requests.put('https://amp-beta.blockstream.com/api/categories/23/registered_users/{}/remove'.format(id), \
                headers={'content-type': 'application/json', 'Authorization': 'token {}'.format(secToken)}).json()
        elif command == 'delete_assignment':
            status = requests.delete('https://amp-beta.blockstream.com/api/assets/{}/assignments/{}/delete'.format(secUuid, id), \
                headers={'content-type': 'application/json', 'Authorization': 'token {}'.format(secToken)}).json()

    investors = []
    res = requests.get('https://amp-beta.blockstream.com/api/registered_users', \
        headers={'content-type': 'application/json', 'Authorization': 'token {}'.format(secToken)}).json()
    cat = requests.get('https://amp-beta.blockstream.com/api/categories/23', \
        headers={'content-type': 'application/json', 'Authorization': 'token {}'.format(secToken)}).json()
    for r in res:
        kyc = (r['id'] in cat['registered_users'])
        investors.append({'id':r['id'], 'name':r['name'], 'gaid':r['GAID'], 'kyc':kyc})

    assignments = []
    res = requests.get('https://amp-beta.blockstream.com/api/assets/{}/assignments'.format(secUuid), \
        headers={'content-type': 'application/json', 'Authorization': 'token {}'.format(secToken)}).json()
    for r in res:
        assignments.append({'id':r['id'], 'registered_user':r['registered_user'], 'amount':r['amount'], 'receiving_address':r['receiving_address'], 'is_distributed':r['is_distributed']})

    logged = False
    if 'logged_in' in session:
        logged = session['logged_in']

    data = {
        'form': True,
        'logged': logged,
        'status': status,
        'investors': investors,
        'assignments': assignments,
    }
    return render_template('investor', **data)

if __name__ == '__main__':
    app.import_name = '.'
    app.config['SECRET_KEY'] = secrets.token_hex(16)
    socketio.run(app, host='0.0.0.0', port=5010)
