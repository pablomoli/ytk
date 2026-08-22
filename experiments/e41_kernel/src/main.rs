//! E41 rung 6 (#184): the two hot loops numpy pays overhead on, in Rust.
//!
//!   sweep  <i8file> <scales.f32> <query.f32> <n> <dim>   int8 brute-force top-10
//!   gather <codes>  <books.f32>  <query.f32> <n> <m> <ks> <d_sub>   PQ ADC top-10
//!
//! Raw little-endian files; scales/books/query are f32 without .npy headers.
//! Prints top-10 as "index score" lines then "elapsed_s <t>".

use memmap2::Mmap;
use std::fs::File;
use std::time::Instant;

const K: usize = 10;

fn read_f32(path: &str) -> Vec<f32> {
    let bytes = std::fs::read(path).unwrap_or_else(|e| panic!("{path}: {e}"));
    bytes
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes([b[0], b[1], b[2], b[3]]))
        .collect()
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
fn dot_i8(row: &[i8], q: &[i8]) -> i32 {
    // i8 x i8 -> i32; LLVM autovectorizes to NEON smull/sadalp on aarch64
    let mut acc: i32 = 0;
    for (a, b) in row.iter().zip(q.iter()) {
        acc += (*a as i32) * (*b as i32);
    }
    acc
}

fn sweep(args: &[String]) {
    let (path, scales_path, q_path) = (&args[0], &args[1], &args[2]);
    let n: usize = args[3].parse().unwrap();
    let dim: usize = args[4].parse().unwrap();

    let scales = read_f32(scales_path);
    let qf = read_f32(q_path);
    assert_eq!(qf.len(), dim);
    assert_eq!(scales.len(), n);
    // quantize the query the same way the corpus was: symmetric per-vector max scale
    let qmax = qf.iter().fold(0f32, |m, v| m.max(v.abs()));
    let qscale = qmax / 127.0;
    let qi: Vec<i8> = qf.iter().map(|v| (v / qscale).round() as i8).collect();

    let file = File::open(path).unwrap();
    let mmap = unsafe { Mmap::map(&file).unwrap() };
    let data: &[i8] = unsafe { std::slice::from_raw_parts(mmap.as_ptr() as *const i8, n * dim) };

    let t0 = Instant::now();
    let best = top10((0..n).map(|i| {
        let row = &data[i * dim..(i + 1) * dim];
        (i, dot_i8(row, &qi) as f32 * scales[i] * qscale)
    }));
    let dt = t0.elapsed().as_secs_f64();
    for (i, s) in best.iter().rev() {
        println!("{i} {s}");
    }
    println!("elapsed_s {dt}");
}

fn gather(args: &[String]) {
    let (codes_path, books_path, q_path) = (&args[0], &args[1], &args[2]);
    let n: usize = args[3].parse().unwrap();
    let m: usize = args[4].parse().unwrap();
    let ks: usize = args[5].parse().unwrap();
    let d_sub: usize = args[6].parse().unwrap();

    let books = read_f32(books_path);
    let qf = read_f32(q_path);
    assert_eq!(books.len(), m * ks * d_sub);
    assert_eq!(qf.len(), m * d_sub);

    // LUT[m][ks] = dot(book[m][ks], q_sub[m]) — built once, outside the timed loop is unfair,
    // inside matches what numpy's per-query einsum pays
    let file = File::open(codes_path).unwrap();
    let mmap = unsafe { Mmap::map(&file).unwrap() };
    let codes: &[u8] = &mmap[..n * m];

    let t0 = Instant::now();
    let mut lut = vec![0f32; m * ks];
    for mi in 0..m {
        let qs = &qf[mi * d_sub..(mi + 1) * d_sub];
        for ki in 0..ks {
            let cb = &books[(mi * ks + ki) * d_sub..(mi * ks + ki + 1) * d_sub];
            lut[mi * ks + ki] = cb.iter().zip(qs.iter()).map(|(a, b)| a * b).sum();
        }
    }
    let best = top10((0..n).map(|i| {
        let row = &codes[i * m..(i + 1) * m];
        let mut s = 0f32;
        for (mi, &c) in row.iter().enumerate() {
            s += lut[mi * ks + c as usize];
        }
        (i, s)
    }));
    let dt = t0.elapsed().as_secs_f64();
    for (i, s) in best.iter().rev() {
        println!("{i} {s}");
    }
    println!("elapsed_s {dt}");
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("sweep") if args.len() == 7 => sweep(&args[2..]),
        Some("gather") if args.len() == 9 => gather(&args[2..]),
        _ => {
            eprintln!("usage: e41-kernel sweep <i8> <scales> <q> <n> <dim>");
            eprintln!("       e41-kernel gather <codes> <books> <q> <n> <m> <ks> <d_sub>");
            std::process::exit(2);
        }
    }
}
