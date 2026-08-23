//! E41 rung 6 (#184): the two hot loops numpy pays overhead on, in Rust.
//!
//!   sweep  <i8file> <scales.f32> <query.f32> <n> <dim>   int8 brute-force top-10
//!   gather <codes>  <books.f32>  <query.f32> <n> <m> <ks> <d_sub>   PQ ADC top-10
//!
//! Raw little-endian files; scales/books/query are f32 without .npy headers.
//! Prints top-10 as "index score" lines then "elapsed_s <t>".

use std::fs::File;
use std::os::unix::fs::FileExt;
use std::time::Instant;

const K: usize = 10;
const IO_BLOCK_BYTES: usize = 4 * 1024 * 1024;

fn decode_f32(bytes: &[u8]) -> Result<Vec<f32>, String> {
    if !bytes.len().is_multiple_of(4) {
        return Err(format!(
            "f32 data length must be a multiple of 4 bytes, got {}",
            bytes.len()
        ));
    }
    Ok(bytes
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes([b[0], b[1], b[2], b[3]]))
        .collect())
}

fn read_f32(path: &str) -> Result<Vec<f32>, String> {
    let bytes = std::fs::read(path).map_err(|error| format!("{path}: {error}"))?;
    decode_f32(&bytes).map_err(|error| format!("{path}: {error}"))
}

#[derive(Clone, Copy, PartialEq)]
struct FileStamp {
    len: u64,
    modified: std::time::SystemTime,
}

fn file_stamp(file: &File, label: &str) -> Result<FileStamp, String> {
    let metadata = file
        .metadata()
        .map_err(|error| format!("{label}: {error}"))?;
    let modified = metadata
        .modified()
        .map_err(|error| format!("{label}: cannot read modification time: {error}"))?;
    Ok(FileStamp {
        len: metadata.len(),
        modified,
    })
}

fn read_exact_at(file: &File, buffer: &mut [u8], offset: u64, label: &str) -> Result<(), String> {
    file.read_exact_at(buffer, offset)
        .map_err(|error| format!("{label}: {error}"))
}

fn ensure_unchanged(file: &File, before: FileStamp, label: &str) -> Result<(), String> {
    if file_stamp(file, label)? != before {
        return Err(format!("{label} changed while being read"));
    }
    Ok(())
}

fn top10(scores: impl Iterator<Item = (usize, f32)>) -> Vec<(usize, f32)> {
    // insertion into a fixed-size sorted buffer; K is tiny so this stays off the profile
    let mut best: Vec<(usize, f32)> = Vec::with_capacity(K + 1);
    for (i, s) in scores {
        if best.len() < K || s > best[0].1 {
            let pos = best.partition_point(|&(_, bs)| bs < s);
            best.insert(pos, (i, s));
            if best.len() > K {
                best.remove(0);
            }
        }
    }
    best
}

#[inline]
fn dot_i8(row: &[u8], q: &[i8]) -> i32 {
    // i8 x i8 -> i32; LLVM autovectorizes to NEON smull/sadalp on aarch64
    let mut acc: i32 = 0;
    for (a, b) in row.iter().zip(q.iter()) {
        acc += (*a as i8 as i32) * (*b as i32);
    }
    acc
}

fn quantize_query(query: &[f32]) -> (Vec<i8>, f32) {
    let max = query
        .iter()
        .fold(0f32, |current, value| current.max(value.abs()));
    if max == 0.0 {
        return (vec![0; query.len()], 0.0);
    }
    let scale = max / 127.0;
    let values = query
        .iter()
        .map(|value| (value / scale).round() as i8)
        .collect();
    (values, scale)
}

fn parse_threads() -> Result<usize, String> {
    match std::env::var("E41_THREADS") {
        Ok(value) => value
            .parse::<usize>()
            .ok()
            .filter(|threads| *threads > 0)
            .ok_or_else(|| "E41_THREADS must be an integer greater than zero".to_owned()),
        Err(std::env::VarError::NotPresent) => Ok(8),
        Err(error) => Err(format!("E41_THREADS: {error}")),
    }
}

fn byte_offset(row: usize, width: usize, label: &str) -> Result<u64, String> {
    row.checked_mul(width)
        .ok_or_else(|| format!("{label} offset overflows usize"))?
        .try_into()
        .map_err(|_| format!("{label} offset overflows u64"))
}

fn sweep_range(
    file: &File,
    range: std::ops::Range<usize>,
    dim: usize,
    scales: &[f32],
    query: &[i8],
    query_scale: f32,
    label: &str,
) -> Result<Vec<(usize, f32)>, String> {
    let (lo, hi) = (range.start, range.end);
    if lo >= hi {
        return Ok(Vec::new());
    }
    let rows_per_block = (IO_BLOCK_BYTES / dim.max(1)).max(1);
    let max_rows = (hi - lo).min(rows_per_block);
    let max_bytes = max_rows
        .checked_mul(dim)
        .ok_or_else(|| format!("{label} block dimensions overflow usize"))?;
    let mut buffer = vec![0u8; max_bytes];
    let mut best = Vec::new();

    for start in (lo..hi).step_by(rows_per_block) {
        let rows = (hi - start).min(rows_per_block);
        let bytes = rows
            .checked_mul(dim)
            .ok_or_else(|| format!("{label} block dimensions overflow usize"))?;
        read_exact_at(
            file,
            &mut buffer[..bytes],
            byte_offset(start, dim, label)?,
            label,
        )?;
        let block_best = top10((0..rows).map(|row_index| {
            let index = start + row_index;
            let row = &buffer[row_index * dim..(row_index + 1) * dim];
            (
                index,
                dot_i8(row, query) as f32 * scales[index] * query_scale,
            )
        }));
        best = top10(best.into_iter().chain(block_best));
    }
    Ok(best)
}

fn sweep(args: &[String]) -> Result<(), String> {
    let (path, scales_path, q_path) = (&args[0], &args[1], &args[2]);
    let n: usize = args[3]
        .parse()
        .map_err(|error| format!("invalid vector count '{}': {error}", args[3]))?;
    let dim: usize = args[4]
        .parse()
        .map_err(|error| format!("invalid dimension '{}': {error}", args[4]))?;

    let scales = read_f32(scales_path)?;
    let qf = read_f32(q_path)?;
    if qf.len() != dim {
        return Err(format!(
            "query length mismatch: expected {dim} f32 values, got {}",
            qf.len()
        ));
    }
    if scales.len() != n {
        return Err(format!(
            "scale length mismatch: expected {n} f32 values, got {}",
            scales.len()
        ));
    }
    let (qi, qscale) = quantize_query(&qf);

    let file = File::open(path).map_err(|error| format!("{path}: {error}"))?;
    let expected_bytes = n
        .checked_mul(dim)
        .ok_or_else(|| "i8 corpus dimensions overflow usize".to_owned())?;
    let before = file_stamp(&file, path)?;
    if before.len != expected_bytes as u64 {
        return Err(format!(
            "i8 corpus length mismatch: expected {expected_bytes} bytes, got {}",
            before.len
        ));
    }

    let threads = parse_threads()?;
    let t0 = Instant::now();
    let chunk = n.div_ceil(threads);
    let mut best: Vec<(usize, f32)> = std::thread::scope(|scope| {
        let handles: Vec<_> = (0..threads)
            .map(|thread| {
                let (lo, hi) = (thread * chunk, ((thread + 1) * chunk).min(n));
                let (file, scales, qi) = (&file, &scales, &qi);
                scope.spawn(move || sweep_range(file, lo..hi, dim, scales, qi, qscale, path))
            })
            .collect();
        handles
            .into_iter()
            .map(|handle| handle.join().unwrap())
            .collect::<Result<Vec<_>, _>>()
            .map(|partials| partials.into_iter().flatten().collect())
    })?;
    best.sort_by(|a, b| a.1.total_cmp(&b.1));
    let best = &best[best.len().saturating_sub(K)..];
    ensure_unchanged(&file, before, path)?;
    let dt = t0.elapsed().as_secs_f64();
    for (i, s) in best.iter().rev() {
        println!("{i} {s}");
    }
    println!("elapsed_s {dt}");
    Ok(())
}

fn checked_product(values: &[usize], label: &str) -> Result<usize, String> {
    values.iter().try_fold(1usize, |product, value| {
        product
            .checked_mul(*value)
            .ok_or_else(|| format!("{label} dimensions overflow usize"))
    })
}

fn adc_lut(
    books: &[f32],
    query: &[f32],
    m: usize,
    ks: usize,
    d_sub: usize,
) -> Result<Vec<f32>, String> {
    let expected_books = checked_product(&[m, ks, d_sub], "PQ books")?;
    if books.len() != expected_books {
        return Err(format!(
            "PQ books length mismatch: expected {expected_books} f32 values, got {}",
            books.len()
        ));
    }
    let expected_query = checked_product(&[m, d_sub], "PQ query")?;
    if query.len() != expected_query {
        return Err(format!(
            "PQ query length mismatch: expected {expected_query} f32 values, got {}",
            query.len()
        ));
    }

    let mut lut = vec![0f32; checked_product(&[m, ks], "PQ LUT")?];
    for mi in 0..m {
        let query_subspace = &query[mi * d_sub..(mi + 1) * d_sub];
        for ki in 0..ks {
            let book = &books[(mi * ks + ki) * d_sub..(mi * ks + ki + 1) * d_sub];
            lut[mi * ks + ki] = book
                .iter()
                .zip(query_subspace.iter())
                .map(|(book_value, query_value)| book_value * query_value)
                .sum();
        }
    }
    Ok(lut)
}

fn adc_scores_from_lut(
    codes: &[u8],
    lut: &[f32],
    n: usize,
    m: usize,
    ks: usize,
) -> Result<Vec<f32>, String> {
    let expected_codes = checked_product(&[n, m], "PQ codes")?;
    if codes.len() != expected_codes {
        return Err(format!(
            "PQ codes length mismatch: expected {expected_codes} bytes, got {}",
            codes.len()
        ));
    }
    let expected_lut = checked_product(&[m, ks], "PQ LUT")?;
    if lut.len() != expected_lut {
        return Err(format!(
            "PQ LUT length mismatch: expected {expected_lut} f32 values, got {}",
            lut.len()
        ));
    }
    if m == 0 {
        return Ok(vec![0.0; n]);
    }
    let mut scores = Vec::with_capacity(n);
    for row in codes.chunks_exact(m) {
        let mut score = 0f32;
        for (mi, &code) in row.iter().enumerate() {
            let code = code as usize;
            if code >= ks {
                return Err(format!(
                    "PQ code {code} at subspace {mi} exceeds codebook size {ks}"
                ));
            }
            score += lut[mi * ks + code];
        }
        scores.push(score);
    }
    Ok(scores)
}

fn gather_top10(
    file: &File,
    n: usize,
    m: usize,
    ks: usize,
    lut: &[f32],
    label: &str,
) -> Result<Vec<(usize, f32)>, String> {
    let rows_per_block = (IO_BLOCK_BYTES / m.max(1)).max(1);
    let max_rows = n.min(rows_per_block);
    let max_bytes = max_rows
        .checked_mul(m)
        .ok_or_else(|| format!("{label} block dimensions overflow usize"))?;
    let mut buffer = vec![0u8; max_bytes];
    let mut best = Vec::new();

    for start in (0..n).step_by(rows_per_block) {
        let rows = (n - start).min(rows_per_block);
        let bytes = rows
            .checked_mul(m)
            .ok_or_else(|| format!("{label} block dimensions overflow usize"))?;
        read_exact_at(
            file,
            &mut buffer[..bytes],
            byte_offset(start, m, label)?,
            label,
        )?;
        let scores = adc_scores_from_lut(&buffer[..bytes], lut, rows, m, ks)?;
        let candidates = scores
            .into_iter()
            .enumerate()
            .map(|(index, score)| (start + index, score));
        best = top10(best.into_iter().chain(candidates));
    }
    Ok(best)
}

fn gather(args: &[String]) -> Result<(), String> {
    let (codes_path, books_path, q_path) = (&args[0], &args[1], &args[2]);
    let n: usize = args[3]
        .parse()
        .map_err(|error| format!("invalid vector count '{}': {error}", args[3]))?;
    let m: usize = args[4]
        .parse()
        .map_err(|error| format!("invalid subspace count '{}': {error}", args[4]))?;
    let ks: usize = args[5]
        .parse()
        .map_err(|error| format!("invalid codebook size '{}': {error}", args[5]))?;
    let d_sub: usize = args[6]
        .parse()
        .map_err(|error| format!("invalid subspace dimension '{}': {error}", args[6]))?;

    let books = read_f32(books_path)?;
    let qf = read_f32(q_path)?;

    let file = File::open(codes_path).map_err(|error| format!("{codes_path}: {error}"))?;
    let expected_codes = checked_product(&[n, m], "PQ codes")?;
    let before = file_stamp(&file, codes_path)?;
    if before.len != expected_codes as u64 {
        return Err(format!(
            "PQ codes length mismatch: expected {expected_codes} bytes, got {}",
            before.len
        ));
    }

    // LUT construction stays inside the timed region to match numpy's per-query einsum cost.
    let t0 = Instant::now();
    let lut = adc_lut(&books, &qf, m, ks, d_sub)?;
    let best = gather_top10(&file, n, m, ks, &lut, codes_path)?;
    ensure_unchanged(&file, before, codes_path)?;
    let dt = t0.elapsed().as_secs_f64();
    for (i, s) in best.iter().rev() {
        println!("{i} {s}");
    }
    println!("elapsed_s {dt}");
    Ok(())
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let result = match args.get(1).map(String::as_str) {
        Some("sweep") if args.len() == 7 => sweep(&args[2..]),
        Some("gather") if args.len() == 9 => gather(&args[2..]),
        _ => {
            eprintln!("usage: e41-kernel sweep <i8> <scales> <q> <n> <dim>");
            eprintln!("       e41-kernel gather <codes> <books> <q> <n> <m> <ks> <d_sub>");
            std::process::exit(2);
        }
    };
    if let Err(error) = result {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn top10_keeps_the_ten_highest_scores_in_ascending_order() {
        let scores = (0..13).map(|index| (index, index as f32 - 4.0));
        let result = top10(scores);
        assert_eq!(
            result,
            vec![
                (3, -1.0),
                (4, 0.0),
                (5, 1.0),
                (6, 2.0),
                (7, 3.0),
                (8, 4.0),
                (9, 5.0),
                (10, 6.0),
                (11, 7.0),
                (12, 8.0),
            ]
        );
    }

    #[test]
    fn dot_i8_accumulates_signed_products_in_i32() {
        assert_eq!(dot_i8(&[(-128_i8) as u8, 127, 3], &[-1, 2, -4]), 370);
    }

    #[test]
    fn positioned_read_rejects_truncation_after_open() {
        let path = std::env::temp_dir().join(format!(
            "e41-kernel-truncate-after-open-{}",
            std::process::id()
        ));
        std::fs::write(&path, [1, 2, 3, 4, 5, 6]).unwrap();
        let file = File::open(&path).unwrap();
        std::fs::OpenOptions::new()
            .write(true)
            .open(&path)
            .unwrap()
            .set_len(5)
            .unwrap();

        let mut buffer = [0; 6];
        let result = read_exact_at(&file, &mut buffer, 0, "test corpus");
        std::fs::remove_file(path).unwrap();
        assert!(result.is_err());
    }

    #[test]
    fn decode_f32_reads_little_endian_values() {
        let bytes = [0x00, 0x00, 0x80, 0x3f, 0x00, 0x00, 0x20, 0xc0];
        assert_eq!(decode_f32(&bytes).unwrap(), vec![1.0, -2.5]);
    }

    #[test]
    fn decode_f32_rejects_trailing_bytes() {
        let bytes = [0x00, 0x00, 0x80, 0x3f, 0xff];
        assert!(decode_f32(&bytes).is_err());
    }

    #[test]
    fn quantize_query_uses_symmetric_max_scale() {
        let (values, scale) = quantize_query(&[1.0, -1.0, 0.5]);
        assert_eq!(values, vec![127, -127, 64]);
        assert_eq!(scale, 1.0 / 127.0);
    }

    #[test]
    fn quantize_query_maps_an_all_zero_query_to_zero() {
        let (values, scale) = quantize_query(&[0.0, 0.0]);
        assert_eq!(values, vec![0, 0]);
        assert_eq!(scale, 0.0);
    }

    #[test]
    fn adc_scores_sum_the_selected_subspace_products() {
        let lut = adc_lut(&[1.0, 3.0, 2.0, -1.0], &[2.0, 4.0], 2, 2, 1).unwrap();
        let scores = adc_scores_from_lut(&[0, 0, 1, 0, 1, 1], &lut, 3, 2, 2).unwrap();
        assert_eq!(scores, vec![10.0, 14.0, 2.0]);
    }
}
