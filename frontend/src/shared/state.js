export const state = {mandateId:null, defaultPortfolio:null, deploymentMode:null, operatorToken:"", displayedInputDecimals:6, displayedOutputDecimals:18, activeMandate:null};
state.demoMode = false;
state.demoToken = "";
export const isReverse = (p) => p?.token_in?.toLowerCase() === state.activeMandate?.token_out?.toLowerCase();
