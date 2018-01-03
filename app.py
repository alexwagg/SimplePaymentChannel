from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash, send_from_directory
import mysql.connector
from web3 import Web3, HTTPProvider
import rlp
import json

import my_connections

app = Flask(__name__)

## set this to your eth node, this is localhost default config
w3 = Web3(HTTPProvider('http://127.0.0.1:8545'))

## payment channel address
channel_address = '0xB4108eb4A6AFEC5179dBBe261e813A7B1d9429C6'
## payment channel abi
channel_abi = json.load(open('./static/abi/PaymentChannelABI.json'))
## initializing the contract with this address
channel_instance = w3.eth.contract(address=channel_address, abi=channel_abi)

@app.route('/', methods=['GET'])
def home():
	return render_template('home.html')

@app.route('/opened-channel', methods=['POST'])
def opened_channel():
	channel_id = request.form['channel_id']

	## now, use our own eth node to verify that the user actually created a channel with the proper deposit
	## also, if the user created a channel, and it isn't in out database, this function will add it.
	success, msg = determine_valid_channel(channel_id)

	return json.dumps({'success': success, 'msg': msg})
	
@app.route('/pay-channel', methods=['POST'])
def pay_channel():
	amt_to_pay = int(request.form['amt_to_pay'])
	channel_id = int(request.form['channel_id'])
	signed_blob = request.form['signed_blob']

	success, msg = determine_valid_channel(channel_id, amt_to_pay)

	if (not success):
		return json.dumps({'success': success, 'msg': msg})

	msg_hash = w3.soliditySha3(['uint256', 'uint256'], [channel_id, amt_to_pay])
	recovered_address = web3.eth.account.recover(msg_hash=msg_hash, signature=signed_blob)

	conn = mysql.connector.connect(user=my_connections.mysql_user, password=my_connections.mysql_pass, host=my_connections.mysql_host, database=my_connections.mysql_dbname)
	cursor = conn.cursor()

	query = 'SELECT payer_address FROM OpenChannels WHERE channel_id = %s'
	rows = cursor.execute(query, (channel_id, )).fetchall()

	with rows[0][0] as actual_address:
		if (recovered_address != actual_address):

			conn.close()
			cursor.close()

			return json.dumps({'success': False, 'msg': 'Not owner of channel'})
		else:
			query = 'UPDATE OpenChannels SET amt_to_pay = %s, signed_blob = %s WHERE channel_id = %s'
			cursor.execute(query, (amt_to_pay, signed_blob, channel_id))
			conn.commit()

			cursor.close()
			conn.close()

			return json.dumps({'success': True, 'msg': 'Channel paid successfully!'})

@app.route('/close-channel', methods=['POST'])
def close_channel_request():
	channel_id = request.form['channel_id']

	## this should probably send to a database where all of the 'requests' sit until the server iterates over
	## then and batch closes them for efficiency reasons, however I'm just gonna immedately call close_channel(channel_id)

	success, msg = close_channel(channel_id)

	return json.dumps({'success': success, 'msg': msg})

def close_channel(channel_id):
	conn = mysql.connector.connect(user=my_connections.mysql_user, password=my_connections.mysql_pass, host=my_connections.mysql_host, database=my_connections.mysql_dbname)
	cursor = conn.cursor()

	query = 'SELECT payer_address, open_timestamp, deposit, paid, signed_blob FROM OpenChannels WHERE channel_id = %s'
	payer_address, open_timestamp, deposit, paid, signed_blob = cursor.execute(query, (channel_id, ))[0]

	if (signed_blob == '' or paid == 0):
		return (False, 'Channel has not been used')

	else:
		## gather the r, s, v values from the signed data
		r = signed_blob[2:66]
		s = signed_blob[66:130]
		v = signed_blob[130:132]

		## build and then send a transaction from the owner address to the contract
		tx_data = channel_instance.buildTransaction({'from':owner}).closeChannel(channel_id, paid, r, s, v)
		tx_data_signed = w3.eth.signTransaction(tx_data, my_connections.owner_privkey)
		tx_data_signed_raw = rlp.encode(tx_data_signed)
		tx_data_signed_raw_hex = w3.toHex(tx_data_signed_raw)
		## sending transaction...
		tx_hash = w3.eth.sendRawTransaction(tx_data_signed_raw_hex)

		## WARNING: we are NOT currently checking is the transaction succeeds... yet
		## we should implement this, either through some async function that callback's when the transaction is mined
		## or through a intermediate table in the database, where we occassionally iterate through the rows, and see if
		## they are successful, and can be added to the ClosedChannels database

		## I'm just gonna add these to the "closed transactions" db, and just assume they were successful

		query = 'INSERT INTO ClosedChannels (channel_id, payer_address, open_timestamp, deposit, paid, close_tx_hash, signed_blob) VALUES %s, %s, %s, %s, %s, %s, %s'
		cursor.execute(query, (channel_id, payer_address, open_timestamp, deposit, paid, tx_hash, signed_blob))
		conn.commit()

		## now delete this entry in the OpenChannels database

		query = 'DELETE FROM OpenChannels WHERE channel_id = %s'
		cursor.execute(query, (channel_id, ))
		conn.commit()

		cursor.close()
		conn.close()

		return (True, 'Channel closed. Thanks!')
		

def determine_valid_channel(channel_id, amt_to_pay=0):
	## returns (bool - valid/invalid channel, string - reason for fail/success)
	## NOTE: if channel is not yet in the database, and is valid, then we add it

	## determine that this channel is valid, ie:
		## is still open
		## has a positive balance
		## hasn't been expired yet
	## NOTE: we are not verifying that the user has access to the private key that has created this channel... yet.

	## get if the channel is closed from blockchain
	is_closed = channel_instance.call().getClosedStatus(channel_id)

	## if the channel is closed, then it is invalid
	if (is_closed):
		return (False, 'Closed channel')

	## get current block timestamp, channel open timestamp, and channel expire timedelta
	latest_timestamp = w3.eth.getBlock('latest').timestamp
	open_timestamp = channel_instance.call().getOpenTime(channel_id)
	expire_timedelta = channel_instance.call().CHANNELLIFETIME()

	## if the channel is expired, or will expire in 6 hours, then this channel is invalid
	if (open_timestamp + expire_timedelta < latest_timestamp - 21600):
		return (False, 'Old channel')

	## open a db connection, and see if this channel has been added to the database yet
	## get payments that have been signed for, to see if user still has the required balance

	conn = mysql.connector.connect(user=my_connections.mysql_user, password=my_connections.mysql_pass, host=my_connections.mysql_host, database=my_connections.mysql_dbname)
	cursor = conn.cursor()

	query = 'SELECT * FROM OpenChannels WHERE channel_id = %s'

	rows = cursor.execute(query, (channel_id, ))
	print(rows)

	with rows[0] as row:
		if (row == []):
			## channel id has not been added to database
			channel_in_db = False
			paid_amt = 0
		else:
			channel_in_db = True
			paid_amt = row['paid']

	## get channel balance from blockchain
	deposit_amt = channel_instance.call().getDeposit(channel_id)

	if (channel_in_db and (paid_amt > deposit_amt or amt_to_pay > deposit_amt)):

		cursor.close()
		conn.close()

		return (False, 'Channel fully paid')

	if (not channel_in_db):
		payer_address = channel_instance.call().getPayer(channel_id)

		## if payer address is zero, then it means that the channel is not opened
		if (payer_address == '0'):

			cursor.close()
			conn.close()

			return (False, 'Channel unopened')

		query = 'INSERT INTO OpenChannels (channel_id, payer_address, open_timestamp, deposit, paid) VALUES (%s, %s, %s, %s, %s)'

		cursor.execute(query, (channel_id, payer_address, open_timestamp, deposit_amt, 0))
		conn.commit()

		cursor.close()
		conn.close()

		return (True, 'Channel added to database')

	cursor.close()
	conn.close()

	return (True, 'Channel in db')

## for debugging purposes
if __name__ == '__main__':
	# app.run(debug=True, host='0.0.0.0')

	print(determine_valid_channel(1))








