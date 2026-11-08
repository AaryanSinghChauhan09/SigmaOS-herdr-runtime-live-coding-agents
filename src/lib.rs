// SPDX-License-Identifier: Apache-2.0
//! SigmaOS-herdr-runtime-live-coding-agents — SigmaOS herdr-runtime-live-coding-agents component inspired by Linux Mint / Omarchy / Arch Linux.
//!
//! Lifecycle state machine: idle -> running -> stopped, fail-fast transitions.
//! Principles: single responsibility, fail-fast, defensive programming,
//! component isolation, stable API, deterministic tests.

#![forbid(unsafe_code)]

use std::fmt;
/// Errors for `ServiceError` operations. Fail-fast: invalid input is rejected.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ServiceError {
    /// Service is already running
    AlreadyRunning,
    /// Service is not running
    NotRunning,
    /// Service name must not be empty
    EmptyName,
}

impl fmt::Display for ServiceError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::AlreadyRunning => write!(f, "service is already running"),
            Self::NotRunning => write!(f, "service is not running"),
            Self::EmptyName => write!(f, "service name must not be empty"),
        }
    }
}

impl std::error::Error for ServiceError {}

/// Service lifecycle state.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ServiceState {
    /// Created but never started.
    Idle,
    /// Currently running.
    Running,
    /// Started then stopped.
    Stopped,
}

/// A supervised service handle.
#[derive(Debug)]
pub struct Service {
    name: String,
    state: ServiceState,
}

impl Service {
    /// Create a service; fails fast on empty name.
    pub fn new(name: impl Into<String>) -> Result<Self, ServiceError> {
        let name = name.into();
        if name.trim().is_empty() { return Err(ServiceError::EmptyName); }
        Ok(Self { name, state: ServiceState::Idle })
    }

    /// Start the service.
    pub fn start(&mut self) -> Result<(), ServiceError> {
        match self.state {
            ServiceState::Running => Err(ServiceError::AlreadyRunning),
            ServiceState::Idle | ServiceState::Stopped => { self.state = ServiceState::Running; Ok(()) }
        }
    }

    /// Stop the service.
    pub fn stop(&mut self) -> Result<(), ServiceError> {
        match self.state {
            ServiceState::Running => { self.state = ServiceState::Stopped; Ok(()) }
            _ => Err(ServiceError::NotRunning),
        }
    }

    /// Current state.
    pub fn state(&self) -> ServiceState { self.state }

    /// Service name.
    pub fn name(&self) -> &str { &self.name }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lifecycle_transitions() {
        let mut s = Service::new("demo").unwrap();
        assert_eq!(s.state(), ServiceState::Idle);
        s.start().unwrap();
        assert_eq!(s.state(), ServiceState::Running);
        s.stop().unwrap();
        assert_eq!(s.state(), ServiceState::Stopped);
    }

    #[test]
    fn double_start_fails() {
        let mut s = Service::new("demo").unwrap();
        s.start().unwrap();
        assert_eq!(s.start(), Err(ServiceError::AlreadyRunning));
    }

    #[test]
    fn stop_when_idle_fails() {
        let mut s = Service::new("demo").unwrap();
        assert_eq!(s.stop(), Err(ServiceError::NotRunning));
    }

    #[test]
    fn empty_name_fails() {
        assert!(Service::new(" ").is_err());
    }

}

/// Backwards-compatible component handle (kept for existing callers/tests).
#[derive(Debug, Default)]
pub struct Component {
    name: &'static str,
}

impl Component {
    /// Create the component handle.
    pub fn new() -> Self {
        Self { name: "SigmaOS Component" }
    }
}
