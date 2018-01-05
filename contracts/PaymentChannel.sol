pragma solidity ^0.4.19;

contract PaymentChannel {

	// owner of the contract
	address public OWNER;
	// recipient of the funds, best to keep as a cold wallet, OWNER address will be hot on the server
	address public TREASURY;
	// used as a unique channel id, increments by 1 every time a channel is opened 
	uint256 public CHANNELCOUNT;
	// expireChannel can be called after this amount of time
	uint256 constant public CHANNELLIFETIME = 5 days;

	mapping (uint256 => ChannelData) channelMapping;

	struct ChannelData {
		address payer;
		uint256 deposit;
		uint256 openTime;
		bool closed;
	}

	event ChannelOpened(address indexed payer, uint256 indexed channelId, uint256 depositAmount);
	event ChannelClosed(address indexed payer, uint256 indexed channelId, uint256 paidAmount, uint256 refundedAmount);
	event ChannelExpired(address indexed payer, uint256 indexed channelId, uint256 refundedAmount);
	
	//////////// initialization function ////////////////////

	function PaymentChannel(address treasuryAddress) public {
		OWNER = msg.sender;
		TREASURY = treasuryAddress;
	}

	//////////////// owner functions /////////////////////

	function changeOwner(address newOwner) public {
		require(msg.sender == OWNER);

		OWNER = newOwner;
	}

	function changeTreasury(address newTreasury) public {
		require(msg.sender == OWNER);

		TREASURY = newTreasury;
	}

	//////////////// view functions //////////////////////////

	function getPayer(uint256 channelId) view public returns(address){
		return channelMapping[channelId].payer;
	}

	function getDeposit(uint256 channelId) view public returns(uint256){
		return channelMapping[channelId].deposit;
	}

	function getOpenTime(uint256 channelId) view public returns(uint256){
		return channelMapping[channelId].openTime;
	}

	function getClosedStatus(uint256 channelId) view public returns(bool){
		return channelMapping[channelId].closed;
	}

	/////////// channel logic functions ///////////////////////

	function createChannel() public payable {
		// require that:
		//		there is a non-zero amount of ether being sent to start the channel
		require(msg.value > 0);

		// increment channel count and use it as a unique id (only get CHANNELCOUNT once to save gas on SLOAD's)
		uint256 channelId = CHANNELCOUNT + 1;
		CHANNELCOUNT = channelId;

		// init the channel with the creation data 
		channelMapping[channelId] = ChannelData({
			payer : msg.sender,
			deposit : msg.value,
			openTime : block.timestamp,
			closed : false
			});

		// log an event 
		ChannelOpened(msg.sender, channelId, msg.value);
	}

	function closeChannel(uint256 channelId, uint256 paidAmount, bytes32 r, bytes32 s, uint8 v) public {
		
		// IMPORTANT: verify that the payer has signed a message permitting the channel owner to subtract their balance by this amount
		address payerAddressVerify = ecrecover(keccak256(channelId, paidAmount), v, r, s);

		// get channel data and save into memory for easy access
		ChannelData memory data = channelMapping[channelId];

		// require that:
		//		the owner of the contract is calling this function
		//		the amount of the payment channel is less than or equal to the deposit amount
		//		the channel has not been closed yet
		//		that the signer of the message has been verified as the opener of the channel 
		require(
			msg.sender == OWNER
			&& paidAmount <= data.deposit
			&& !data.closed
			&& data.payer == payerAddressVerify
			);

		// set the channel to closed 
		channelMapping[channelId].closed = true;

		// calculate the refund amount 
		uint256 refundAmount = data.deposit - paidAmount;

		// transfer the paid amount to the treasury
		TREASURY.transfer(paidAmount);

		// if the paid amount isn't equal to the deposit, then send this amount to the payer 
		// TODO: catch .send() fails and add them to an array so that the payer can call a function to pull the funds
		if (refundAmount > 0){
			data.payer.send(refundAmount);
		}

		// log an event that the channel was closed
		ChannelClosed(data.payer, channelId, paidAmount, refundAmount);

	}

	function expireChannel(uint256 channelId) public {
		// safe this in memory for cheap access
		ChannelData memory data = channelMapping[channelId];
		// require that:
		//		the address field is not zero (would designate that a channel hasn't been created with this ID)
		//		the owner of the contract, or the opener of the payment channel is calling this function
		//		the channel has been opened more than CHANNELLIFETIME ago
		//		the channel has not been closed previously
		require(
			data.payer != address(0)
			&& (msg.sender == OWNER || msg.sender == data.payer)
			&& block.timestamp > data.openTime + CHANNELLIFETIME
			&& !data.closed);

		// set the channel to closed
		channelMapping[channelId].closed = true;

		// transfer the whole deposit to the payer of the channel
		// TODO: catch .send() fails and add them to an array so that the payer can call a function to pull the funds
		data.payer.send(data.deposit);

		// log an event 
		ChannelExpired(data.payer, channelId, data.deposit);
	}

	// WARMING: ONLY FOR TESTING! REMOVE THIS FOR LIFE DEPLOYMENT!
	function selfDestruct() public{
		require(msg.sender == OWNER);

		selfdestruct(msg.sender);
	}

	////////////// end contract ////////////////////////////
}