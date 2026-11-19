export const state = {mandateId:null, defaultPortfolio:null, deploymentMode:"MOCK", operatorToken:"", displayedInputDecimals:6, displayedOutputDecimals:18, activeMandate:null};
export const isReverse = (p) => p?.token_in?.toLowerCase() === state.activeMandate?.token_out?.toLowerCase();
