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
		this.initWeb3();
		this.bindClicks();
	},

	bindClicks: function(){

		$('#start-channel').click(function(){
			this.startChannel();
		})
		$('#start-watching').click(function(){
			this.startWatching();
		})
		$('#stop-watching').click(function(){
			this.stopWatching();
		})
		$('#close-channel').click(function(){
			this.closeChannel();
		})
	},

	initWeb3: function(){
		// slight delay for variable load times
        setTimeout(function(){
            if (typeof web3 !== 'undefined'){
                console.log('getting web3');
                this.web3Provider = web3.currentProvider;
            }
            else {
            	// we could attempt to connect to a local node here, but AFAIK you can't connect to a local node 
            	// via http when you are serving a page with https, and we would probably want to serve pages with https for our site.
                console.log('No Web3 instance given!');
                // flash modal saying "please download Metamask"
            }

            return this.initContract(web3);

        }, 500);
	},

	initContract: function(web3){
		$.getJSON('./static/abi/PaymentChannelABI.json', function(data){
			// initialize the contract and store as a local variable
			this.Contract = web3.eth.contract(data);
			this.contractInstance = this.Contract.at('0xb4108eb4a6afec5179dbbe261e813a7b1d9429c6');
		});
	},

	startChannel: function(){
		// this function sends a transaction, via web3, to the blockchain starting a payment channel and depositing 0.1 ether
		// once/if the transaction if successful, then the function will report to to the server that a channel has been started with 
		// the corresponsing channel id, and the amount that has been deposited
		this.recurringCharge = web3.toWei(1, "finney");
		this.channelDeposit = web3.toWei(0.1, "ether");

		this.contractInstance.methods.createChannel().send({value: this.channelDeposit, from: web3.eth.accounts[0]})
			.on('transactionHash', function(hash){
				console.log("your transaction has been submitted, please check http://kovan.etherscan.com/tx/" + hash + " for it's current status.")
			})
			.on('receipt', function(receipt){
				console.log(receipt);
			})
			.on('error', function(error){
				console.log('error while starting channel', error);
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