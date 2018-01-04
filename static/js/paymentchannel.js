// Thanks to @xavierlepretre for providing the basis of this function
// https://gist.github.com/xavierlepretre/88682e871f4ad07be4534ae560692ee6

// This allows you to poll for a transaction receipt being mined, and allows you to 
// circumvent the faulty metamask event watchers.
// In standard web3.js, a getTransactionReceipt returns null if the tx has not been
// mined yet. This will only return the actual receipt after the tx has been mined.

function getTransactionReceiptMined(txHash) {
    const self = this;
    const transactionReceiptAsync = function(resolve, reject) {
        web3.eth.getTransactionReceipt(txHash, (error, receipt) => {
            if (error) {
                reject(error);
            } else if (receipt == null) {
                setTimeout(
                    () => transactionReceiptAsync(resolve, reject), 500);
            } else {
                resolve(receipt);
            }
        });
    }
    return new Promise(transactionReceiptAsync);
};



PaymentChannel = {
	// save the web3 provider
	web3Provider: null,
	// initialize the contract, and store as local variables
	Contract: null,
	contractInstance: null,
	// local variables for payment channel logic
	channelId: null,
	channelDeposit: null,
	channelPendingCharge: null,
	recurringCharge: null,


	init: function(){
		PaymentChannel.initWeb3();
		PaymentChannel.bindClicks();
	},

	bindClicks: function(){

		$('#start-channel').click(function(){
			PaymentChannel.startChannel();
		})
		$('#start-watching').click(function(){
			PaymentChannel.startWatching();
		})
		$('#stop-watching').click(function(){
			PaymentChannel.stopWatching();
		})
		$('#close-channel').click(function(){
			PaymentChannel.closeChannel();
		})
	},

	initWeb3: function(){
		// slight delay for variable load times
        setTimeout(function(){
            if (typeof web3 !== 'undefined'){
                console.log('getting web3');
                PaymentChannel.web3Provider = web3.currentProvider;
            }
            else {
            	// we could attempt to connect to a local node here, but AFAIK you can't connect to a local node 
            	// via http when you are serving a page with https, and we would probably want to serve pages with https for our site.
                console.log('No Web3 instance given!');
                // flash modal saying "please download Metamask"
            }

            return PaymentChannel.initContract(web3);

        }, 500);
	},

	initContract: function(web3){
		$.getJSON('./static/abi/PaymentChannelABI.json', function(data){
			// initialize the contract and store as a local variable
			PaymentChannel.Contract = web3.eth.contract(data);
			PaymentChannel.contractInstance = PaymentChannel.Contract.at('0xb4108eb4a6afec5179dbbe261e813a7b1d9429c6');
		});
	},

	startChannel: function(){
		// this function sends a transaction, via web3, to the blockchain starting a payment channel and depositing 0.1 ether
		// once/if the transaction if successful, then the function will report to to the server that a channel has been started with 
		// the corresponsing channel id, and the amount that has been deposited
		PaymentChannel.recurringCharge = web3.toWei(1, "finney");
		PaymentChannel.channelDeposit = web3.toWei(0.0000001, "ether");
		console.log(PaymentChannel.contractInstance)
		PaymentChannel.contractInstance.createChannel({gas:150000, value: PaymentChannel.channelDeposit, from: web3.eth.accounts[0]}, async function(error, result){
			if (error){
				console.log('could not create payment channel', error)
			}
			else {
				txHash = result;
				txReceipt = await getTransactionReceiptMined(txHash);
				console.log(txReceipt);
				if (txReceipt.logs === []){
					console.log('transaction failed! check etherscan for more info');
				}
				else {
					startChannelLog = txReceipt.logs[0];
					console.log(startChannelLog);
					channelId = startChannelLog.topics[2];
					console.log(channelId);
					$.post('opened-channel', {'channel_id': channelId}, function(data, status){
						console.log(status, data);
					})
				}
			}
		});
	},

	startWatching: function(){
		// this function signs a message with the first deposit to the channel (0.001 ether), and the server will report back with 
		// success, then the payment channel is live, and this process of signing a message for (last message amt + 0.001 ether) will
		// repeat every 30 seconds
	},

	stopWatching: function(){
		// this function will simply break stop the charges from occuring. basically the same as exiting the webpage
	},

	closeChannel: function(){
		// this function will send a request to the server to close the payment channel
		// of course, a user cannot close the channel with their acct. but this just expedites the charge/refund process 
		// by requesting that the server closes the channel instead of waiting for the script that runs every... day/2 days(?) 
		// to close the channel
	}

}

$(document).ready(function(){
	PaymentChannel.init();
})