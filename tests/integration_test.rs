// Integration test for SigmaOS-herdr-runtime-live-coding-agents
// Verifies the crate builds and links as a dependency.
#![allow(unused_imports)]

use sigmaos_herdr_runtime_live_coding_agents as _;

#[test]
fn crate_links_and_runs() {
    assert_eq!(2 + 2, 4);
}
