// PROTOTYPE (grove workshop) - throwaway until a look wins a real spec.
// A crafted leaf: bezier outline -> earcut triangulation (THREE.Shape) ->
// CPU cup-and-curl so the card is a curved 3D surface, not a flat billboard.
// One geometry, thousands of instances - the crafted-not-sprite foliage core.
import { BufferGeometry, Float32BufferAttribute, Shape, ShapeGeometry, Vector3 } from 'three'

export type LeafShapeParams = {
  length: number // leaf length along +y, world units
  width: number // max half-width factor of length
  cup: number // lateral curl (across the leaf)
  curl: number // lengthwise droop of the tip
}

export const DEFAULT_LEAF: LeafShapeParams = { length: 0.22, width: 0.38, cup: 0.5, curl: 0.45 }

export function buildLeafGeometry(params: LeafShapeParams): BufferGeometry {
  const L = params.length
  const W = params.length * params.width
  // lanceolate outline: stem -> wide shoulder -> tip, mirrored by beziers
  const shape = new Shape()
  shape.moveTo(0, 0)
  shape.bezierCurveTo(W * 0.55, L * 0.12, W, L * 0.42, W * 0.28, L * 0.82)
  shape.quadraticCurveTo(W * 0.1, L * 0.95, 0, L)
  shape.quadraticCurveTo(-W * 0.1, L * 0.95, -W * 0.28, L * 0.82)
  shape.bezierCurveTo(-W, L * 0.42, -W * 0.55, L * 0.12, 0, 0)
  const geometry: BufferGeometry = new ShapeGeometry(shape, 3)
  // cup across the width, curl the tip downward - gives the card a real
  // silhouette from every angle and normals that catch the rim light
  const pos = geometry.getAttribute('position')
  const uv: number[] = []
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i)
    const y = pos.getY(i)
    const across = x / Math.max(1e-5, W)
    const along = y / L
    pos.setZ(i, params.cup * W * across * across + params.curl * L * along * along * 0.35)
    uv.push(across * 0.5 + 0.5, along)
  }
  geometry.setAttribute('uv', new Float32BufferAttribute(uv, 2))
  geometry.computeVertexNormals()
  return geometry
}

// Instance transform basis: leaves feather outward from the branch, seated on
// the twig surface, rotated around the tangent so a site's K leaves fan.
export function leafBasis(tangent: Vector3, normal: Vector3, spin: number, pitch: number): { xAxis: Vector3; yAxis: Vector3; zAxis: Vector3 } {
  const binormal = new Vector3().crossVectors(tangent, normal).normalize()
  const radial = normal.clone().multiplyScalar(Math.cos(spin)).add(binormal.clone().multiplyScalar(Math.sin(spin))).normalize()
  // leaf +y points outward-and-along: blend radial with the branch direction
  const yAxis = radial.clone().multiplyScalar(Math.cos(pitch)).add(tangent.clone().multiplyScalar(Math.sin(pitch))).normalize()
  const zAxis = new Vector3().crossVectors(yAxis, tangent).normalize()
  if (zAxis.lengthSq() < 1e-6) zAxis.copy(normal)
  const xAxis = new Vector3().crossVectors(yAxis, zAxis).normalize()
  return { xAxis, yAxis, zAxis }
}
