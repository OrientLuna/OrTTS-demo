//! Run unchanged against cooperative, v1-token, and pre-token native libraries.
use ortts_engine::{
    cancellation::{capabilities, CancelHandle, CancelMode, CancelOutcome, Task},
    Engine, Error,
};

#[test]
fn precancelled_load_is_structured_and_single_use() {
    let mut task = Task::new().unwrap();
    let handle = task.cancel_handle();
    assert_eq!(handle.cancel(), CancelOutcome::Requested);
    let result = Engine::new_cancellable(
        "/does/not/exist",
        "P3",
        None,
        &"a".repeat(64),
        4,
        false,
        &mut task,
    );
    assert!(matches!(result, Err(Error::Cancelled)));
    assert_eq!(handle.cancel(), CancelOutcome::Inactive);
    assert!(matches!(
        Engine::new_cancellable("/unused", "P3", None, &"a".repeat(64), 4, false, &mut task),
        Err(Error::TaskConsumed)
    ));
}

#[test]
fn error_does_not_leave_an_active_cancel_handle() {
    let mut task = Task::new().unwrap();
    let handle = task.cancel_handle();
    let result = Engine::new_cancellable("bad\0root", "P3", None, "bad", 4, false, &mut task);
    assert!(matches!(result, Err(Error::InvalidInput(_))));
    assert_eq!(handle.cancel(), CancelOutcome::Inactive);
}

#[test]
fn dropped_ticket_makes_external_handle_inert() {
    fn send_sync<T: Send + Sync>() {}
    send_sync::<CancelHandle>();
    let task = Task::new().unwrap();
    let handle = task.cancel_handle();
    drop(task);
    assert_eq!(
        std::thread::spawn(move || handle.cancel()).join().unwrap(),
        CancelOutcome::Inactive
    );
}

#[test]
fn capabilities_report_expected_runtime() {
    let actual = capabilities();
    if let Ok(expected) = std::env::var("ORTTS_EXPECT_CANCEL_MODE") {
        match expected.as_str() {
            "cooperative" => {
                assert_eq!(actual.loading, CancelMode::Cooperative);
                assert_eq!(actual.synthesis, CancelMode::Cooperative);
            }
            "v1" => {
                assert_eq!(actual.loading, CancelMode::Cooperative);
                assert_eq!(actual.synthesis, CancelMode::DiscardAfterReturn);
            }
            "legacy" => {
                assert_eq!(actual.loading, CancelMode::DiscardAfterReturn);
                assert_eq!(actual.synthesis, CancelMode::DiscardAfterReturn);
            }
            _ => panic!("unknown test mode"),
        }
    }
    eprintln!("Cancellation capabilities: {actual:?}");
}
