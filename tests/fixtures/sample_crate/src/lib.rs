//! A small crate for testing the slow tools.

/// Adds two numbers.
pub fn add(left: u32, right: u32) -> u32 {
    double_free_sum(left, right)
}

fn double_free_sum(left: u32, right: u32) -> u32 {
    left + right
}

/// Says how big a value is.
pub fn describe(value: u32) -> String {
    if value > 10 {
        format!("big value {value}")
    } else {
        "small value".to_string()
    }
}

/// No test calls this.
pub fn untested(value: u32) -> u32 {
    value * 3
}

/// A test calls this and checks nothing about the result.
pub fn weakly_tested(value: u32) -> u32 {
    value.max(7)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn adds() {
        assert_eq!(add(1, 2), 3);
    }

    #[test]
    fn pins_wording() {
        assert_eq!(describe(1), "small value");
    }

    #[test]
    fn runs_it() {
        weakly_tested(1);
    }
}
