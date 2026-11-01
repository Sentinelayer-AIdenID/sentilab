/**
 * AIdenID Classifier — versioned, deterministic request classification for merchant bundles.
 *
 * Exports: describeRequest, deterministicTriage, classifyRequest, operatorFromHint,
 * and the shared type definitions (RequestVector, EdgeIdentity, Triage, etc.).
 *
 * Pure functions with no env, no network except the bounded directory fetch in the
 * Web Bot Auth verifier (web-bot-auth.ts). Semver: 1.0.0.
 */

// Re-export types and functions consumed by merchants + the aquarium edge.
             
                
              
             
         
               
                
           
                
          
                    

export { describeRequest } from "./describe-request.js";
export { deterministicTriage, classifyRequest, operatorFromHint } from "./deterministic-triage.js";
export { userAgentFamily } from "./recognized-automation.js";
// Web Bot Auth verifier — consumed by aquarium-edge (no fork).
export {
  SIGNER_TO_OPERATOR,
  verifyWebBotAuth,
  verifyWorkerRequest,
  captureSignatureEvidence,
  normalizeSignatureEvidence,
  recheckSignatureEvidence,
} from "./web-bot-auth.mjs";
export const VERSION = "1.1.0";
