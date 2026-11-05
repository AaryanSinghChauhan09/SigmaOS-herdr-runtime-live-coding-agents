#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AgentTask {
    pub agent_id: String,
    pub prompt: String,
    pub is_completed: bool,
}

#[derive(Debug, Default)]
pub struct HerdrCoordinator {
    tasks: Vec<AgentTask>,
}

impl HerdrCoordinator {
    pub fn new() -> Self { Self { tasks: Vec::new() } }
    pub fn spawn_task(&mut self, agent_id: &str, prompt: &str) -> usize {
        let idx = self.tasks.len();
        self.tasks.push(AgentTask {
            agent_id: agent_id.to_string(),
            prompt: prompt.to_string(),
            is_completed: false,
        });
        idx
    }
    pub fn complete_task(&mut self, idx: usize) {
        if let Some(t) = self.tasks.get_mut(idx) {
            t.is_completed = true;
        }
    }
    pub fn active_task_count(&self) -> usize {
        self.tasks.iter().filter(|t| !t.is_completed).count()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_herdr_coordinator_aaa() {
        // Arrange
        let mut coord = HerdrCoordinator::new();
        // Act
        let t0 = coord.spawn_task("agent-1", "Refactor memory allocator");
        let _t1 = coord.spawn_task("agent-2", "Run test suite");
        assert_eq!(coord.active_task_count(), 2);
        coord.complete_task(t0);
        // Assert
        assert_eq!(coord.active_task_count(), 1);
    }
}
