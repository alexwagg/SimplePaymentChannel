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
channel_address = '0x19bee2ce208ae4f1a333cffc80976349d22b35f5'
## payment channel abi
channel_abi = json.load(open('./static/abi/PaymentChannelABI.json'))
## initializing the contract with this address
channel_instance = w3.eth.contract(address=channel_address, abi=channel_abi)
## MANDATORY PAYMENT in Wei, obviously this shouldn't be hardcoded, but for now...
PAYMENT_SIZE = 1000000000000000

@app.route('/', methods=['GET'])
def home():
	return render_template('home.html')

@app.route('/opened-channel', methods=['POST'])
def opened_channel():
	try:
		channel_id = w3.toInt(hexstr = request.form['channel_id'])
	except:
		return json.dumps({'success': False, 'msg': 'Channel ID must be hex-encoded'})

	## now, use our own eth node to verify that the user actually created a channel with the proper deposit
	## also, if the user created a channel, and it isn't in out database, this function will add it.
	success, msg, deposit, paid = determine_valid_channel(channel_id)

	return json.dumps({'success': success, 'msg': msg, 'deposit': deposit, 'paid': paid})
	
@app.route('/pay-channel', methods=['POST'])
def pay_channel():
	amt_to_pay = int(request.form['amt_to_pay'])
	channel_id = int(request.form['channel_id'])
	## remove 0x... from signed blob
	signed_blob = request.form['signed_blob']

	## check if this channel is valid, and insert into the database if we do not have it
	## this could occur if a user did not use our front-end to create a channel, but directly used the blockchain
	success, msg, deposit, paid = determine_valid_channel(channel_id, amt_to_pay)

	if (not success):
		return json.dumps({'success': success, 'msg': msg})

	## retreive the r, s, v values from the signed blob
	r = w3.toBytes(hexstr=signed_blob[2:66])
	s = w3.toBytes(hexstr=signed_blob[66:130])
	v = w3.toInt(hexstr=signed_blob[130:])

	try:
		recovered_address = channel_instance.call().testECRecover(channel_id, amt_to_pay, r, s, v);
	except:
		return json.dumps({'success': False, 'msg': 'Cannot ECRecover these values', 'deposit': deposit, 'paid': paid})


	conn = mysql.connector.connect(user=my_connections.mysql_user, password=my_connections.mysql_pass, host=my_connections.mysql_host, database=my_connections.mysql_dbname)
	cursor = conn.cursor()

	query = 'SELECT payer_address, paid, deposit FROM OpenChannels WHERE channel_id = %s'
	cursor.execute(query, (channel_id, ))
	rows = cursor.fetchall()

	actual_address, paid, deposit = rows[0]

	## force the payment to be correct... this actually is covered by the ec recover (wouldn't return correct address if payment size was incorrect)
	## but we can give a better error message this way
	if (paid + PAYMENT_SIZE != amt_to_pay):

		conn.close()
		cursor.close()

		return json.dumps({'success': False, 'msg': 'Incorrect payment size.', 'deposit': deposit, 'paid': paid})

	elif (recovered_address != actual_address):

		conn.close()
		cursor.close()

		return json.dumps({'success': False, 'msg': 'Not owner of channel', 'deposit': deposit, 'paid': paid})

	else:
		query = 'UPDATE OpenChannels SET paid = %s, signed_blob = %s WHERE channel_id = %s'
		cursor.execute(query, (amt_to_pay, signed_blob, channel_id))
		conn.commit()

		cursor.close()
		conn.close()

		return json.dumps({'success': True, 'msg': 'Channel paid successfully!', 'deposit': deposit, 'paid': amt_to_pay})

@app.route('/close-channel', methods=['POST'])
def close_channel_request():
	try:
		channel_id = int(request.form['channel_id'])
	except:
		return json.dumps({'success': False, 'msg': 'Bad channel id.', 'deposit': 0, 'paid': 0})

	## this should probably send to a database where all of the 'requests' sit until the server iterates over
	## them and batch closes them for efficiency reasons, however I'm just gonna immedately call close_channel(channel_id)

	success, msg, deposit, paid = close_channel(channel_id)

	return json.dumps({'success': success, 'msg': msg, 'deposit': deposit, 'paid': paid})

def close_channel(channel_id):
	conn = mysql.connector.connect(user=my_connections.mysql_user, password=my_connections.mysql_pass, host=my_connections.mysql_host, database=my_connections.mysql_dbname)
	cursor = conn.cursor()

	## get the data for this specific channel
	query = 'SELECT payer_address, open_timestamp, deposit, paid, signed_blob FROM OpenChannels WHERE channel_id = %s'
	cursor.execute(query, (channel_id, ))
	rows = cursor.fetchall()

	## if no rows exist, then this channel doesn't exist yet and can't be closed
	if (rows == [] or rows == None):
		return (False, 'Channel does not exist in database', 0, 0)

	else:
		payer_address, open_timestamp, deposit, paid, signed_blob = rows[0]

		if (signed_blob == '' or paid == 0):
			return (False, 'Channel has not been used', deposit, 0)

		else:
			## retreive the r, s, v values from the signed blob
			r = w3.toBytes(hexstr=signed_blob[2:66])
			s = w3.toBytes(hexstr=signed_blob[66:130])
			v = w3.toInt(hexstr=signed_blob[130:])

			## build and then send a transaction from the owner address to the contract
			tx_hash = str(channel_instance.transact({'from':my_connections.owner_pubkey}).closeChannel(channel_id, paid, r, s, v))
			# ## signing and sending transaction...

			## WARNING: we are NOT currently checking is the transaction succeeds... yet
			## we should implement this, either through some async function that callback's when the transaction is mined
			## or through a intermediate table in the database, where we occassionally iterate through the rows, and see if
			## they are successful, and can be added to the ClosedChannels database

			## I'm just gonna add these to the "closed transactions" db, and just assume they were successful

			query = 'INSERT INTO ClosedChannels (channel_id, payer_address, open_timestamp, deposit, paid, close_tx_hash, signed_blob) VALUES (%s, %s, %s, %s, %s, %s, %s)'
			cursor.execute(query, (channel_id, payer_address, open_timestamp, deposit, paid, tx_hash, signed_blob))
			conn.commit()

			## now delete this entry in the OpenChannels database

			query = 'DELETE FROM OpenChannels WHERE channel_id = %s'
			cursor.execute(query, (channel_id, ))
			conn.commit()

			cursor.close()
			conn.close()

			return (True, 'Channel closed at transaction: ' + tx_hash +'. Thanks!', deposit, paid)
		

def determine_valid_channel(channel_id, amt_to_pay=0):
	## returns (bool - valid/invalid channel, string - reason for fail/success, int deposit_amount, int paid_amt)
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
		return (False, 'Closed channel', 0, 0)

	## get current block timestamp, channel open timestamp, and channel expire timedelta
	latest_timestamp = w3.eth.getBlock('latest').timestamp
	open_timestamp = channel_instance.call().getOpenTime(channel_id)
	expire_timedelta = channel_instance.call().CHANNELLIFETIME()

	## if the channel is expired, or will expire in 6 hours, then this channel is invalid
	if (open_timestamp + expire_timedelta < latest_timestamp - 21600):
		return (False, 'Old channel', 0, 0)

	## open a db connection, and see if this channel has been added to the database yet
	## get payments that have been signed for, to see if user still has the required balance

	conn = mysql.connector.connect(user=my_connections.mysql_user, password=my_connections.mysql_pass, host=my_connections.mysql_host, database=my_connections.mysql_dbname)
	cursor = conn.cursor()

	query = 'SELECT paid FROM OpenChannels WHERE channel_id = %s'

	cursor.execute(query, (channel_id, ))

	rows = cursor.fetchall()

	## get deposit amount from blockchain
	deposit_amt = channel_instance.call().getDeposit(channel_id)

	## channel not in db, so we have no payment data
	if (rows == [] or rows == None):
		payer_address = channel_instance.call().getPayer(channel_id)

		## if payer address is zero, then it means that the channel is not opened
		if (payer_address == '0'):

			cursor.close()
			conn.close()

			return (False, 'Channel unopened', 0, 0)

		query = 'INSERT INTO OpenChannels (channel_id, payer_address, open_timestamp, deposit, paid) VALUES (%s, %s, %s, %s, %s)'

		cursor.execute(query, (channel_id, payer_address, open_timestamp, deposit_amt, 0))
		conn.commit()

		cursor.close()
		conn.close()

		return (True, 'Channel added to database', deposit_amt, 0)

	## if channel is in db, then we need to check that there is still "space" in the channel to transact
	else:
		paid_amt = rows[0][0]

		if (paid_amt > deposit_amt or amt_to_pay > deposit_amt):
			cursor.close()
			conn.close()

			return (False, 'Channel fully paid', deposit_amt, paid_amt)
		else:
			cursor.close()
			conn.close()

			return (True, 'Channel in db', deposit_amt, paid_amt)
	

## for debugging purposes
if __name__ == '__main__':
	app.run(debug=True, host='0.0.0.0')









