var PaymentChannel = artifacts.require("./contracts/PaymentChannel.sol");

module.exports = function(deployer, network, accounts) {
	if (network == 'development'){
		deployer.deploy(PaymentChannel, accounts[1]);
	}
}