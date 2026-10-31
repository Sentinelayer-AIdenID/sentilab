// A thin adapter: the reviewed contract remains the sole projection implementation.
import { project } from '../contracts/contract-0.2/evidence-projection.mjs';
let input = '';
for await (const chunk of process.stdin) input += chunk;
process.stdout.write(JSON.stringify(project(JSON.parse(input))));
