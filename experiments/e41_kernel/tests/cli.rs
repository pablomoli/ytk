use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT_FIXTURE: AtomicU64 = AtomicU64::new(0);

struct FixtureDir {
    path: PathBuf,
}

impl FixtureDir {
    fn new(name: &str) -> Self {
        let sequence = NEXT_FIXTURE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "e41-kernel-{name}-{}-{sequence}",
            std::process::id()
        ));
        fs::create_dir(&path).expect("create fixture directory");
        Self { path }
    }

    fn path(&self, name: &str) -> PathBuf {
        self.path.join(name)
    }
}

impl Drop for FixtureDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.path);
    }
}

fn write_f32(path: &Path, values: &[f32]) {
    let bytes: Vec<u8> = values
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect();
    fs::write(path, bytes).expect("write f32 fixture");
}

fn command(args: &[String], threads: Option<&str>) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_e41-kernel"));
    command.args(args).env_remove("E41_THREADS");
    if let Some(threads) = threads {
        command.env("E41_THREADS", threads);
    }
    command.output().expect("run e41-kernel")
}

fn sweep_fixture(query: &[f32]) -> (FixtureDir, Vec<String>) {
    let fixture = FixtureDir::new("sweep");
    let corpus = fixture.path("corpus.i8");
    let scales = fixture.path("scales.f32");
    let query_path = fixture.path("query.f32");
    let corpus_bytes: Vec<u8> = [1_i8, 2, -3, 4, 5, -6]
        .into_iter()
        .map(|value| value as u8)
        .collect();
    fs::write(&corpus, corpus_bytes).expect("write sweep corpus");
    write_f32(&scales, &[0.5, 1.0, 0.25]);
    write_f32(&query_path, query);
    let args = vec![
        "sweep".into(),
        corpus.display().to_string(),
        scales.display().to_string(),
        query_path.display().to_string(),
        "3".into(),
        "2".into(),
    ];
    (fixture, args)
}

fn gather_fixture() -> (FixtureDir, Vec<String>) {
    let fixture = FixtureDir::new("gather");
    let codes = fixture.path("codes.u8");
    let books = fixture.path("books.f32");
    let query = fixture.path("query.f32");
    fs::write(&codes, [0, 0, 1, 0, 1, 1]).expect("write gather codes");
    write_f32(&books, &[1.0, 3.0, 2.0, -1.0]);
    write_f32(&query, &[2.0, 4.0]);
    let args = vec![
        "gather".into(),
        codes.display().to_string(),
        books.display().to_string(),
        query.display().to_string(),
        "3".into(),
        "2".into(),
        "2".into(),
        "1".into(),
    ];
    (fixture, args)
}

fn ranking(output: &Output) -> Vec<(usize, f32)> {
    assert!(
        output.status.success(),
        "command failed\nstdout: {}\nstderr: {}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    String::from_utf8(output.stdout.clone())
        .expect("stdout is UTF-8")
        .lines()
        .filter(|line| !line.starts_with("elapsed_s "))
        .map(|line| {
            let mut fields = line.split_whitespace();
            let index = fields
                .next()
                .expect("ranking index")
                .parse()
                .expect("integer ranking index");
            let score = fields
                .next()
                .expect("ranking score")
                .parse()
                .expect("float ranking score");
            assert!(fields.next().is_none(), "unexpected ranking field");
            (index, score)
        })
        .collect()
}

#[test]
fn invalid_usage_exits_two_and_prints_both_forms() {
    let output = command(&[], None);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert_eq!(output.status.code(), Some(2));
    assert!(stderr.contains("e41-kernel sweep"));
    assert!(stderr.contains("e41-kernel gather"));
}

#[test]
fn tiny_sweep_matches_the_reference_formula() {
    let (_fixture, args) = sweep_fixture(&[1.0, -1.0]);
    let result = ranking(&command(&args, Some("1")));
    assert_eq!(result, vec![(2, 2.75), (0, -0.5), (1, -7.0)]);
}

#[test]
fn sweep_results_match_with_one_and_two_threads() {
    let (_fixture, args) = sweep_fixture(&[1.0, -1.0]);
    assert_eq!(
        ranking(&command(&args, Some("1"))),
        ranking(&command(&args, Some("2")))
    );
}

#[test]
fn sweep_with_more_threads_than_rows_matches_single_thread() {
    let (_fixture, args) = sweep_fixture(&[1.0, -1.0]);
    assert_eq!(
        ranking(&command(&args, Some("1"))),
        ranking(&command(&args, Some("8")))
    );
}

#[test]
fn zero_threads_is_rejected_before_the_sweep() {
    let (_fixture, args) = sweep_fixture(&[1.0, -1.0]);
    let output = command(&args, Some("0"));
    assert_eq!(output.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&output.stderr)
        .contains("E41_THREADS must be an integer greater than zero"));
}

#[test]
fn all_zero_query_produces_zero_sweep_scores() {
    let (_fixture, args) = sweep_fixture(&[0.0, 0.0]);
    let result = ranking(&command(&args, Some("1")));
    assert_eq!(result.len(), 3);
    assert!(result.iter().all(|(_, score)| *score == 0.0));
}

#[test]
fn malformed_f32_trailing_bytes_are_rejected() {
    let (fixture, args) = sweep_fixture(&[1.0, -1.0]);
    let scales = fixture.path("scales.f32");
    let mut bytes = fs::read(&scales).expect("read scales fixture");
    bytes.push(0);
    fs::write(scales, bytes).expect("write malformed scales fixture");

    let output = command(&args, Some("1"));
    assert_eq!(output.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&output.stderr).contains("multiple of 4 bytes"));
}

#[test]
fn short_sweep_corpus_is_rejected_before_slicing() {
    let (fixture, args) = sweep_fixture(&[1.0, -1.0]);
    fs::write(fixture.path("corpus.i8"), [1, 2, 3, 4, 5]).expect("shorten sweep corpus");

    let output = command(&args, Some("1"));
    assert_eq!(output.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&output.stderr)
        .contains("i8 corpus length mismatch: expected 6 bytes, got 5"));
}

#[test]
fn tiny_gather_matches_the_reference_adc_formula() {
    let (_fixture, args) = gather_fixture();
    let result = ranking(&command(&args, None));
    assert_eq!(result, vec![(1, 14.0), (0, 10.0), (2, 2.0)]);
}

#[test]
fn short_gather_codes_are_rejected_before_slicing() {
    let (fixture, args) = gather_fixture();
    fs::write(fixture.path("codes.u8"), [0, 0, 1, 0, 1]).expect("shorten gather codes");

    let output = command(&args, None);
    assert_eq!(output.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&output.stderr)
        .contains("PQ codes length mismatch: expected 6 bytes, got 5"));
}
