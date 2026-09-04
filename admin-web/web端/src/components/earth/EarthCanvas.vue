<!--
  EarthCanvas — Phase 2 Three.js 真实感地球
  - 经纬度 → Three.js Vector3(贴球面)
  - 真实纹理(白天地表 / 凹凸 / 海洋高光)通过在线 CDN
  - PhongMaterial + 太阳光 + 环境光(昼夜明暗)
  - 独立云层球体(自转比地球快)
  - 大气 ShaderMaterial(边缘蓝色散射 Fresnel)
  - OrbitControls(鼠标拖拽 / 滚轮缩放 / 自动自转)
  - 12 城经纬度节点 + DOM 城市标签(背面隐藏)
  - 6 球面大圆弧线(slerp,弧高贴合球面) + 流光粒子
  - 极光(南北极 ShaderMaterial Fresnel)
  - 卫星(轨道 + 尾迹)
  - 流星(随机拖尾)
  - 星空粒子背景
  - 窗口 resize 自适应 + 抗锯齿
-->
<template>
  <div ref="wrapEl" class="earth-wrap">
    <canvas ref="canvasEl" class="earth-canvas"></canvas>
    <!-- DOM 城市标签层(挂在 canvas 之上,不在 WebGL 内) -->
    <div ref="overlayEl" class="city-overlay">
      <div
        v-for="c in cities"
        :key="c.name"
        :ref="(el) => { if (el) cityLabelEls[c.name] = el as HTMLElement }"
        class="city-label"
        :style="{ color: c.color.getStyle(), borderColor: c.color.getStyle() + '88' }"
      >{{ c.name }}</div>
    </div>
    <!-- 顶部 loading 提示(贴图加载时显示) -->
    <div v-if="loading" class="loading-tip">
      <span class="dot" /> 加载地球贴图中…
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 真实感地球渲染(Three.js WebGL)
 * 关键步骤:
 *   1. Scene + Camera + Renderer(antialias 开启)
 *   2. OrbitControls 鼠标拖拽 / 滚轮缩放 / 自动自转
 *   3. 球体 + 真实纹理(CDN)+ PhongMaterial
 *   4. 独立云层球(自转比地球快 1.2-1.3x)
 *   5. 大气 ShaderMaterial(Fresnel 蓝色散射)
 *   6. 极光 ShaderMaterial(南北极 Fresnel)
 *   7. 太阳光 + 环境光
 *   8. 城市节点(Sprite 挂 scene,始终朝向相机)
 *   9. 弧线(slerp 球面大圆,弧高) + 流光粒子
 *   10. 卫星(轨道 + 尾迹)
 *   11. 流星(随机拖尾)
 *   12. DOM 城市标签(背面隐藏)
 *   13. resize 自适应
 */
import { ref, onMounted, onBeforeUnmount, reactive } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

/* ============== 配置 ============== */
const EARTH_RADIUS = 50        // 地球半径
const ATMOSPHERE_RADIUS = 53  // 大气层半径(略大 6%)
const CLOUD_RADIUS = 50.6      // 云层半径(略大 1.2%)
const ROTATION_SPEED = 0.0008  // 地球自转速度(弧度/帧)
const CLOUD_ROTATION_SPEED = 0.0012  // 云层自转(比地球快 1.5x)
const AMBIENT_LIGHT_INTENSITY = 0.18 // 环境光强度(微弱,不要冲淡昼夜对比)
const SUN_LIGHT_INTENSITY = 1.4     // 太阳光强度

const FLOW_PARTICLES_PER_ARC = 4      // 每条弧线上的流光粒子数
const FLOW_PARTICLE_T_STEP = 0.001    // 每帧 t 增量(到 1 时归零)
const SATELLITE_ORBIT_PERIOD = 90     // 卫星轨道周期(秒)
const SATELLITE_SPAWN_INTERVAL = 4    // 每 4 秒生成一颗卫星
const SATELLITE_MAX = 5               // 卫星数量上限(超过回收最早的)
const SATELLITE_TRAIL_LENGTH = 30     // 卫星尾迹点数

const METEOR_TRAIL_LENGTH = 30        // 流星拖尾段数
const METEOR_MAX = 3                  // 流星数量上限
const METEOR_SPEED_MIN = 0.5          // 流星最小速度(每帧)
const METEOR_SPEED_MAX = 1.0          // 流星最大速度(每帧)
const METEOR_LIFE_MIN = 3             // 流星最短寿命(秒)
const METEOR_LIFE_MAX = 4             // 流星最长寿命(秒)
const METEOR_SPAWN_MIN = 6            // 流星最小生成间隔(秒)
const METEOR_SPAWN_MAX = 10           // 流星最大生成间隔(秒)

// === 火箭(从地面随机城市起飞到太空) ===
const ROCKET_SPAWN_MIN = 18            // 火箭最小生成间隔(秒)
const ROCKET_SPAWN_MAX = 30           // 火箭最大生成间隔(秒)
const ROCKET_DURATION_MIN = 6          // 飞行秒数(从地面到 1.8 倍地球半径)
const ROCKET_DURATION_MAX = 9
const ROCKET_FLAME_LENGTH = 12         // 尾焰段数

const AURORA_RADIUS_INNER = 51        // 极光环内径(地球表面外 1 半径 — 极光贴着地表)
const AURORA_RADIUS_OUTER = 55        // 极光环外径(地球表面外 5 半径 — 薄薄一层)
const AURORA_HEIGHT_ABOVE = 3         // 极光离地表的微小偏移(已在 RingGeometry 半径里)

/* ============== 12 城经纬度 ============== */
const cities = reactive(
  /* 全球 45+ 主要城市,飞线/火箭每次随机选起点和终点 — 避免重复 */
  [
    // 中国
    { name: '北京',     lng: 116.4,  lat: 39.9  },
    { name: '上海',     lng: 121.5,  lat: 31.2  },
    { name: '广州',     lng: 113.3,  lat: 23.1  },
    { name: '成都',     lng: 104.1,  lat: 30.7  },
    { name: '深圳',     lng: 114.1,  lat: 22.5  },
    { name: '杭州',     lng: 120.2,  lat: 30.3  },
    { name: '香港',     lng: 114.2,  lat: 22.3  },
    { name: '乌鲁木齐', lng: 87.6,   lat: 43.8  },
    // 东亚/东南亚
    { name: '东京',     lng: 139.7,  lat: 35.7  },
    { name: '首尔',     lng: 127.0,  lat: 37.6  },
    { name: '新加坡',   lng: 103.8,  lat: 1.3   },
    { name: '吉隆坡',   lng: 101.7,  lat: 3.1   },
    { name: '雅加达',   lng: 106.8,  lat: -6.2  },
    { name: '马尼拉',   lng: 121.0,  lat: 14.6  },
    { name: '曼谷',     lng: 100.5,  lat: 13.7  },
    { name: '胡志明市', lng: 106.7,  lat: 10.8  },
    // 南亚/中亚
    { name: '孟买',     lng: 72.9,   lat: 19.0  },
    { name: '新德里',   lng: 77.2,   lat: 28.6  },
    { name: '迪拜',     lng: 55.3,   lat: 25.3  },
    { name: '伊斯坦布尔', lng: 29.0, lat: 41.0 },
    { name: '德黑兰',   lng: 51.4,   lat: 35.7  },
    { name: '利雅得',   lng: 46.7,   lat: 24.7  },
    // 欧洲
    { name: '伦敦',     lng: -0.1,   lat: 51.5  },
    { name: '巴黎',     lng: 2.3,    lat: 48.9  },
    { name: '柏林',     lng: 13.4,   lat: 52.5  },
    { name: '罗马',     lng: 12.5,   lat: 41.9  },
    { name: '马德里',   lng: -3.7,   lat: 40.4  },
    { name: '莫斯科',   lng: 37.6,   lat: 55.8  },
    { name: '伊斯坦布尔2', lng: 28.9, lat: 41.0 },
    { name: '阿姆斯特丹', lng: 4.9,  lat: 52.4  },
    { name: '维也纳',   lng: 16.4,   lat: 48.2  },
    { name: '苏黎世',   lng: 8.5,    lat: 47.4  },
    { name: '哥本哈根', lng: 12.6,   lat: 55.7  },
    { name: '斯德哥尔摩', lng: 18.1, lat: 59.3 },
    // 北美
    { name: '纽约',     lng: -74.0,  lat: 40.7  },
    { name: '旧金山',   lng: -122.4, lat: 37.8  },
    { name: '洛杉矶',   lng: -118.2, lat: 34.0  },
    { name: '西雅图',   lng: -122.3, lat: 47.6  },
    { name: '多伦多',   lng: -79.4,  lat: 43.7  },
    { name: '温哥华',   lng: -123.1, lat: 49.3  },
    { name: '芝加哥',   lng: -87.6,  lat: 41.9  },
    { name: '墨西哥城', lng: -99.1,  lat: 19.4  },
    { name: '波哥大',   lng: -74.1,  lat: 4.7   },
    // 南美
    { name: '圣保罗',   lng: -46.6,  lat: -23.5 },
    { name: '布宜诺斯艾利斯', lng: -58.4, lat: -34.6 },
    { name: '圣地亚哥', lng: -70.6,  lat: -33.4 },
    { name: '利马',     lng: -77.0,  lat: -12.0 },
    // 非洲
    { name: '开罗',     lng: 31.2,   lat: 30.0  },
    { name: '约翰内斯堡', lng: 28.0, lat: -26.2 },
    { name: '内罗毕',   lng: 36.8,   lat: -1.3  },
    { name: '卡萨布兰卡', lng: -7.6, lat: 33.6  },
    { name: '拉各斯',   lng: 3.4,    lat: 6.5   },
    // 大洋洲
    { name: '悉尼',     lng: 151.2,  lat: -33.9 },
    { name: '墨尔本',   lng: 144.9,  lat: -37.8 },
    { name: '奥克兰',   lng: 174.8,  lat: -36.8 }
  ].map((c) => ({
    ...c,
    color: new THREE.Color(['#7c5cff', '#ff7849', '#34d399', '#fbbf24', '#a78bfa'][Math.floor(Math.random() * 5)])
  }))
)

/* 6 弧线 */
// === 飞线 cooldown 跟踪:避免同对城市短时间重复出现 ===
const recentArcPairs: Array<[number, number, number]> = []  // [ai, bi, simTime]
const ARC_COOLDOWN = 20  // 秒(同一对城市 20 秒内不重复)

/* 选一对未在 cooldown 中的城市对 */
function pickRandomArcPair(): [number, number] {
  for (let attempt = 0; attempt < 20; attempt++) {
    const ai = Math.floor(Math.random() * cities.length)
    const bi = Math.floor(Math.random() * cities.length)
    if (ai === bi) continue
    const pair: [number, number] = ai < bi ? [ai, bi] : [bi, ai]
    if (recentArcPairs.some(([a, b]) => a === pair[0] && b === pair[1])) continue
    return pair
  }
  // fallback:任意不同城市
  const ai = Math.floor(Math.random() * cities.length)
  let bi = Math.floor(Math.random() * cities.length)
  while (bi === ai) bi = Math.floor(Math.random() * cities.length)
  return ai < bi ? [ai, bi] : [bi, ai]
}

/* ============== 状态 ============== */
const wrapEl = ref<HTMLDivElement | null>(null)
const canvasEl = ref<HTMLCanvasElement | null>(null)
const overlayEl = ref<HTMLDivElement | null>(null)
const cityLabelEls: Record<string, HTMLElement | null> = reactive({})
const loading = ref(true)

let scene: THREE.Scene
let camera: THREE.PerspectiveCamera
let renderer: THREE.WebGLRenderer
let controls: OrbitControls
let earthMesh: THREE.Mesh
let cloudMesh: THREE.Mesh
let atmosphereMesh: THREE.Mesh
let cityMeshes: THREE.Sprite[] = []
let arcLines: THREE.Line[] = []
let arcFlowData: ArcFlowData[] = []
let auroraMeshes: THREE.Mesh[] = []
let auroraMaterials: THREE.ShaderMaterial[] = []
let satellites: SatelliteData[] = []
let meteors: MeteorData[] = []
let rockets: RocketData[] = []
let starField: THREE.Points
let animFrameId: number
let resizeObserver: ResizeObserver
let resumeTimer: number | null = null  // 拖拽闲置恢复 autoRotate 用(模块级,unmount 可见)

/* 时间管理 */
let clock: THREE.Clock
let simTime = 0                // 累计仿真时间(秒)
let nextSatelliteTime = SATELLITE_SPAWN_INTERVAL  // 下一颗卫星生成时间
let nextMeteorTime = 6         // 第一颗流星在 6-10 秒后出现
let nextRocketTime = 12         // 第一枚火箭在 12-30 秒后出现(同时间不重复)

/* ============== 类型 ============== */
interface ArcFlowData {
  points: THREE.Points
  tValues: number[]
  arcPoints: THREE.Vector3[]
}

interface SatelliteData {
  mesh: THREE.Mesh
  trail: THREE.Line
  angle: number       // 当前公转角
  height: number      // 离地心半径
  yOffset: number     // 赤道上下偏移
}

interface RocketData {
  group: THREE.Group   // 火箭 group(头+身体+尾翼+尾焰,整体朝向路径方向)
  curve: THREE.CatmullRomCurve3  // 飞行路径
  t: number             // 0-1 当前进度
  duration: number      // 飞行秒数
  startTime: number     // simTime 起点
  city: typeof cities[number]  // 从哪个城市起飞
}

interface MeteorData {
  line: THREE.Line
  positions: THREE.Vector3[]  // 30 个点(头部最前,尾部最暗)
  velocity: THREE.Vector3
  life: number         // 已存活时间(秒)
  maxLife: number      // 总寿命(秒)
}

/* ============== 工具函数 ============== */
/** 经纬度 → Three.js 球面 Vector3(贴球面) */
function latLonToVec3(lat: number, lon: number, r: number): THREE.Vector3 {
  const phi = (90 - lat) * Math.PI / 180      // 维度角(从北极起)
  const theta = (lon + 180) * Math.PI / 180  // 经度角
  return new THREE.Vector3(
    -r * Math.sin(phi) * Math.cos(theta),
     r * Math.cos(phi),
     r * Math.sin(phi) * Math.sin(theta)
  )
}

/** 球面大圆 slerp 插值(返回 N 个点 + 弧高贴合球面) */
function sphereArc(
  a: THREE.Vector3, b: THREE.Vector3,
  segments: number, lift: number, r: number
): THREE.Vector3[] {
  const points: THREE.Vector3[] = []
  for (let i = 0; i <= segments; i++) {
    const t = i / segments
    const slerped = a.clone().lerp(b.clone(), t).normalize()
    // 弧高: 弧线紧贴地球表层(lift=0.12 时,弧顶比地表高 12% 半径 ≈ 6000km,有"飞"的感觉但不飘出大气层)
    const height = r * (1 + Math.sin(t * Math.PI) * lift)
    points.push(slerped.multiplyScalar(height))
  }
  return points
}

/** 加载在线 CDN 纹理(带回退) */
async function loadTexture(
  primaryUrl: string,
  fallbackUrl?: string
): Promise<THREE.Texture> {
  return new Promise((resolve, reject) => {
    const loader = new THREE.TextureLoader()
    loader.setCrossOrigin('anonymous')
    loader.load(
      primaryUrl,
      (tex) => resolve(tex),
      undefined,
      (err) => {
        console.warn(`[EarthCanvas] 纹理加载失败 ${primaryUrl},尝试 fallback`)
        if (fallbackUrl) {
          loader.load(fallbackUrl, resolve, undefined, reject)
        } else {
          reject(err)
        }
      }
    )
  })
}

/** 多重 fallback 加载(按顺序尝试,首个成功即返回;都失败返回 null) */
async function loadTextureChain(urls: string[]): Promise<THREE.Texture | null> {
  for (const url of urls) {
    try {
      const tex = await loadTexture(url)
      console.log(`[EarthCanvas] 贴图 OK: ${url}`)
      return tex
    } catch (e) {
      console.warn(`[EarthCanvas] 贴图失败: ${url}`)
    }
  }
  return null
}

/**
 * 安全释放材质(支持 Material | Material[])
 *  - @types/three 0.185+ 的 Mesh/Line.material 类型是联合类型,需手动 narrow
 */
function disposeMaterial(mat: THREE.Material | THREE.Material[] | undefined): void {
  if (!mat) return
  if (Array.isArray(mat)) mat.forEach((m) => m.dispose())
  else mat.dispose()
}

/* ============== 星空 ============== */
function createStarField(): THREE.Points {
  const geometry = new THREE.BufferGeometry()
  const positions: number[] = []
  const colors: number[] = []
  for (let i = 0; i < 2000; i++) {
    // 距离 200-300 范围(地球外很远)
    const r = 200 + Math.random() * 100
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos(2 * Math.random() - 1)
    positions.push(
      r * Math.sin(phi) * Math.cos(theta),
      r * Math.sin(phi) * Math.sin(theta),
      r * Math.cos(phi)
    )
    // 颜色随机(蓝白)
    const c = 0.5 + Math.random() * 0.5
    colors.push(c, c, c * (0.9 + Math.random() * 0.1))
  }
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3))
  return new THREE.Points(geometry, new THREE.PointsMaterial({
    size: 0.6,
    vertexColors: true,
    sizeAttenuation: true,
    transparent: true,
    opacity: 0.9
  }))
}

/* ============== 地球 + 大气 + 云 ============== */
function createEarth(earthMap: THREE.Texture, bumpMap?: THREE.Texture, specMap?: THREE.Texture) {
  const geometry = new THREE.SphereGeometry(EARTH_RADIUS, 96, 64)
  const material = new THREE.MeshPhongMaterial({
    map: earthMap,
    bumpMap: bumpMap,
    bumpScale: 2.5,                        // ← 升级:1.2 → 2.5(凹凸更立体)
    specularMap: specMap,
    specular: new THREE.Color(0x333333),
    shininess: 12,
  })
  return new THREE.Mesh(geometry, material)
}

function createAtmosphere(): THREE.Mesh {
  const geometry = new THREE.SphereGeometry(ATMOSPHERE_RADIUS, 96, 64)
  const material = new THREE.ShaderMaterial({
    vertexShader: `
      varying vec3 vNormal;
      varying vec3 vPositionNormal;
      void main() {
        vNormal = normalize(normalMatrix * normal);
        vPositionNormal = normalize((modelViewMatrix * vec4(position, 1.0)).xyz);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      varying vec3 vNormal;
      varying vec3 vPositionNormal;
      uniform vec3 glowColor;
      void main() {
        float intensity = pow(0.72 - dot(vNormal, vPositionNormal), 2.0);
        gl_FragColor = vec4(glowColor, 1.0) * intensity * 1.4;
      }
    `,
    uniforms: { glowColor: { value: new THREE.Color(0x6bb6ff) } },
    side: THREE.BackSide,
    blending: THREE.AdditiveBlending,
    transparent: true,
    depthWrite: false
  })
  return new THREE.Mesh(geometry, material)
}

function createClouds(cloudMap: THREE.Texture): THREE.Mesh {
  const geometry = new THREE.SphereGeometry(CLOUD_RADIUS, 96, 64)
  const material = new THREE.MeshPhongMaterial({
    map: cloudMap,
    transparent: true,
    opacity: 0.4,
    depthWrite: false,
    side: THREE.DoubleSide
  })
  return new THREE.Mesh(geometry, material)
}

/* ============== 火箭(从地面起飞,沿曲线到太空) ============== */
function createRocket(city: typeof cities[number]): RocketData {
  // 整个火箭 group 朝路径切线方向,内部部件用局部坐标
  const group = new THREE.Group()

  // 头部 — 圆锥(银色金属)
  const noseGeo = new THREE.ConeGeometry(0.6, 1.5, 16)
  const bodyMat = new THREE.MeshPhongMaterial({
    color: 0xeeeeee, specular: 0xaaaaaa, shininess: 80
  })
  const nose = new THREE.Mesh(noseGeo, bodyMat)
  nose.position.y = 2.5
  group.add(nose)

  // 主体 — 圆柱(白)
  const bodyGeo = new THREE.CylinderGeometry(0.5, 0.5, 2.0, 16)
  const body = new THREE.Mesh(bodyGeo, bodyMat)
  body.position.y = 0.7
  group.add(body)

  // 尾翼 — 4 个小方块
  const finMat = new THREE.MeshPhongMaterial({ color: 0xcccccc })
  for (let i = 0; i < 4; i++) {
    const finGeo = new THREE.BoxGeometry(0.05, 0.5, 0.6)
    const fin = new THREE.Mesh(finGeo, finMat)
    const a = (i / 4) * Math.PI * 2
    fin.position.set(Math.cos(a) * 0.6, -0.5, Math.sin(a) * 0.6)
    fin.rotation.y = a
    group.add(fin)
  }

  // 尾焰 — 多段 Line(头部亮,尾部淡),沿 -Y 方向
  const flameGroup = new THREE.Group()
  for (let i = 0; i < ROCKET_FLAME_LENGTH; i++) {
    const t = i / ROCKET_FLAME_LENGTH
    // y 从 -0.5 到 -6 渐远,alpha 从 1 到 0
    const geo = new THREE.BufferGeometry()
    const positions = new Float32Array([
      0, -0.5 - i * 0.45, 0,
      0, -0.95 - i * 0.45, 0
    ])
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    const mat = new THREE.LineBasicMaterial({
      color: new THREE.Color(1.0 - t * 0.3, 0.6 - t * 0.5, 0.1 - t * 0.1),
      transparent: true,
      opacity: 1.0 - t,
      blending: THREE.AdditiveBlending
    })
    const seg = new THREE.Line(geo, mat)
    flameGroup.add(seg)
  }
  flameGroup.position.y = -0.3
  group.add(flameGroup)

  // 计算飞行路径(从该城市到太空 1.8 倍地球半径,中间控制点随机偏移)
  const start = latLonToVec3(city.lat, city.lng, EARTH_RADIUS * 1.01)
  const endDir = new THREE.Vector3(
    Math.cos(city.lat * Math.PI / 180) * Math.cos(city.lng * Math.PI / 180),
    Math.sin(city.lat * Math.PI / 180),
    Math.cos(city.lat * Math.PI / 180) * Math.sin(city.lng * Math.PI / 180)
  ).normalize()
  const mid = start.clone().lerp(start.clone().add(endDir), 0.5).normalize().multiplyScalar(EARTH_RADIUS * 1.4)
  const end = start.clone().add(endDir).normalize().multiplyScalar(EARTH_RADIUS * 1.8)

  const curve = new THREE.CatmullRomCurve3([start, mid, end], false, 'catmullrom', 0.5)

  // 初始位置 + 朝向
  const pos0 = curve.getPointAt(0)
  const tan0 = curve.getTangentAt(0).normalize()
  group.position.copy(pos0)
  // 让 +Y 方向对准切线(rotateZ 让 Y 轴沿方向)
  const quat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), tan0)
  group.quaternion.copy(quat)

  return {
    group: new THREE.Group(),
    curve,
    t: 0,
    duration: 0,
    startTime: 0,
    city
  }
}

/* ============== 极光(南北极 Fresnel 渐变 + 波形脉动) ============== */
function createAurora(): THREE.Mesh {
  // RingGeometry 默认在 XY 平面,绕地轴平躺需要绕 X 旋转 -π/2
  const geometry = new THREE.RingGeometry(
    AURORA_RADIUS_INNER,
    AURORA_RADIUS_OUTER,
    64,            // 圆周分段
    8              // 径向分段(让色带平滑过渡)
  )
  const material = new THREE.ShaderMaterial({
    uniforms: {
      colorNear: { value: new THREE.Color(0x5bffb8) },  // 内圈绿(地球真实极光色)
      colorMid:  { value: new THREE.Color(0xa980ff) },  // 中圈紫
      colorFar:  { value: new THREE.Color(0x5b8cff) },  // 外圈蓝
      time:      { value: 0 }
    },
    vertexShader: `
      varying vec3 vNormal;
      varying vec3 vViewDir;
      varying vec2 vUv;
      void main() {
        vNormal = normalize(normalMatrix * normal);
        vec4 mvPos = modelViewMatrix * vec4(position, 1.0);
        vViewDir = normalize(-mvPos.xyz);
        vUv = uv;
        gl_Position = projectionMatrix * mvPos;
      }
    `,
    fragmentShader: `
      uniform vec3 colorNear;
      uniform vec3 colorMid;
      uniform vec3 colorFar;
      uniform float time;
      varying vec3 vNormal;
      varying vec3 vViewDir;
      varying vec2 vUv;
      void main() {
        // Fresnel:边缘亮,中心弱 → 极光像帷幕
        float fresnel = 1.0 - abs(dot(vNormal, vViewDir));
        fresnel = pow(fresnel, 2.0);
        // 径向渐变(uv.x: 内→外)— 主体绿 → 紫
        vec3 col = mix(colorNear, colorMid, smoothstep(0.0, 0.55, vUv.x));
        col = mix(col, colorFar, smoothstep(0.55, 1.0, vUv.x));
        // 沿圆周方向的波形脉动(uv.y 是角向坐标)
        float wave = 0.65 + 0.35 * sin(vUv.y * 10.0 + time * 1.4);
        // 大幅降低透明度(0.55 → 0.22)— 极光应该细腻,不是大色块
        gl_FragColor = vec4(col * fresnel * wave, fresnel * 0.22);
      }
    `,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide
  })
  return new THREE.Mesh(geometry, material)
}

/* ============== 城市节点:Sprite(挂 scene,不挂 earthMesh) ============== */

/**
 * 程序化生成精灵光晕纹理(64x64):
 *  - 中心纯白 + 亮蓝白,向外径向衰减
 *  - 边缘完全透明,无硬边
 */
function createGlowTexture(centerColor: string = '#bce0ff'): THREE.Texture {
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = size; canvas.height = size
  const ctx = canvas.getContext('2d')!
  const cx = size / 2, cy = size / 2
  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, size / 2)
  grad.addColorStop(0.0, '#ffffff')
  grad.addColorStop(0.15, centerColor)
  grad.addColorStop(0.35, centerColor + '88')
  grad.addColorStop(0.7, centerColor + '22')
  grad.addColorStop(1.0, centerColor + '00')
  ctx.fillStyle = grad
  ctx.fillRect(0, 0, size, size)
  const tex = new THREE.CanvasTexture(canvas)
  tex.needsUpdate = true
  return tex
}

/**
 * 升级:Sprite 现在挂到 scene(不是 earthMesh)
 *  - Sprite 始终朝向相机,位置在球面上但不随地球旋转
 *  - depthTest: false 永远不被其他几何体挡住
 */
function createCities(): THREE.Sprite[] {
  const sprites: THREE.Sprite[] = []
  const glowTex = createGlowTexture('#bce0ff')
  cities.forEach((c) => {
    const pos = latLonToVec3(c.lat, c.lng, EARTH_RADIUS * 1.005)
    const mat = new THREE.SpriteMaterial({
      map: glowTex,
      color: c.color,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      sizeAttenuation: true,
      opacity: 0.95
    })
    const sprite = new THREE.Sprite(mat)
    sprite.position.copy(pos)
    sprite.scale.set(3.5, 3.5, 1)
    sprite.userData = { name: c.name, baseColor: c.color }
    scene.add(sprite)              // ← 升级:挂 scene
    sprites.push(sprite)
  })
  return sprites
}

/* ============== 弧线 + 流光粒子 ============== */

/**
 * 在弧线上创建流光粒子
 *  - 每个粒子有 t 值(0-1),沿弧线推进
 *  - 每帧 t += 0.001,到 1 时归零
 *  - 粒子用 Points + PointsMaterial 加法混合,颜色跟弧线一致
 */
function createFlowParticles(arcPoints: THREE.Vector3[]): ArcFlowData {
  const positions = new Float32Array(FLOW_PARTICLES_PER_ARC * 3)
  const tValues: number[] = []
  // 错开初始 t,让粒子分散开
  for (let i = 0; i < FLOW_PARTICLES_PER_ARC; i++) {
    tValues.push(i / FLOW_PARTICLES_PER_ARC)
  }
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  ;(geo.attributes.position as THREE.BufferAttribute).setUsage(THREE.DynamicDrawUsage)
  const mat = new THREE.PointsMaterial({
    color: 0x6e8eff,               // 跟弧线一致(淡蓝紫)
    size: 1.6,
    sizeAttenuation: true,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false
  })
  const points = new THREE.Points(geo, mat)
  return { points, tValues, arcPoints }
}

/** 每帧推进所有弧线流光粒子位置 */
function updateFlowParticles() {
  for (const fp of arcFlowData) {
    const positions = fp.points.geometry.attributes.position as THREE.BufferAttribute
    const arr = positions.array as Float32Array
    const lastIdx = fp.arcPoints.length - 1
    for (let i = 0; i < fp.tValues.length; i++) {
      fp.tValues[i] = (fp.tValues[i] + FLOW_PARTICLE_T_STEP) % 1
      const t = fp.tValues[i]
      // 把 t 映射到 arcPoints 的位置(弧线分段索引)
      const segPos = t * lastIdx
      const segIdx = Math.min(Math.floor(segPos), lastIdx - 1)
      const segT = segPos - segIdx
      const a = fp.arcPoints[segIdx]
      const b = fp.arcPoints[segIdx + 1]
      arr[i * 3]     = a.x + (b.x - a.x) * segT
      arr[i * 3 + 1] = a.y + (b.y - a.y) * segT
      arr[i * 3 + 2] = a.z + (b.z - a.z) * segT
    }
    positions.needsUpdate = true
  }
}

function createArcs(): THREE.Line[] {
  const lines: THREE.Line[] = []
  // 选 6 对不重复的城市(用 pickRandomArcPair + cooldown)
  const usedPairs: Set<string> = new Set()
  for (let i = 0; i < 6; i++) {
    const [ai, bi] = pickRandomArcPair()
    const key = `${ai}-${bi}`
    if (usedPairs.has(key)) { i--; continue }
    usedPairs.add(key)
    // 记录 cooldown
    recentArcPairs.push([ai, bi, 0]) // simTime 后面 update 时更新

    const a = latLonToVec3(cities[ai].lat, cities[ai].lng, EARTH_RADIUS)
    const b = latLonToVec3(cities[bi].lat, cities[bi].lng, EARTH_RADIUS)
    const points = sphereArc(a, b, 64, 0.12, EARTH_RADIUS)
    const geo = new THREE.BufferGeometry().setFromPoints(points)
    const mat = new THREE.LineBasicMaterial({
      color: 0x6e8eff,
      transparent: true,
      opacity: 0.6,
      blending: THREE.AdditiveBlending
    })
    const line = new THREE.Line(geo, mat)
    earthMesh.add(line)
    lines.push(line)

    // 流光粒子(跟着弧线走)
    const flow = createFlowParticles(points)
    earthMesh.add(flow.points)
    arcFlowData.push(flow)
  }
  return lines
}

/* ============== 卫星(Sphere + 公转 + 尾迹) ============== */
function spawnSatellite() {
  const geo = new THREE.SphereGeometry(0.4, 16, 16)
  const mat = new THREE.MeshPhongMaterial({
    color: 0xaabbcc,
    emissive: 0x6688aa,
    emissiveIntensity: 0.5,
    shininess: 80
  })
  const mesh = new THREE.Mesh(geo, mat)

  // 随机起始角 + 高度(低轨道,赤道附近 5-10 单位)
  const angle = Math.random() * Math.PI * 2
  const height = EARTH_RADIUS + 5 + Math.random() * 5
  const yOffset = (Math.random() - 0.5) * 4   // 小幅上下偏移
  mesh.position.set(
    height * Math.cos(angle),
    yOffset,
    height * Math.sin(angle)
  )

  // 尾迹:动态 BufferGeometry,30 段细白线
  const trailGeo = new THREE.BufferGeometry()
  const trailPositions = new Float32Array(SATELLITE_TRAIL_LENGTH * 3)
  // 初始全部填当前位置(尾迹还没生成)
  for (let i = 0; i < SATELLITE_TRAIL_LENGTH; i++) {
    trailPositions[i * 3]     = mesh.position.x
    trailPositions[i * 3 + 1] = mesh.position.y
    trailPositions[i * 3 + 2] = mesh.position.z
  }
  trailGeo.setAttribute('position', new THREE.BufferAttribute(trailPositions, 3))
  ;(trailGeo.attributes.position as THREE.BufferAttribute).setUsage(THREE.DynamicDrawUsage)
  const trailMat = new THREE.LineBasicMaterial({
    color: 0xffffff,
    transparent: true,
    opacity: 0.45,
    blending: THREE.AdditiveBlending,
    depthWrite: false
  })
  const trail = new THREE.Line(trailGeo, trailMat)

  scene.add(mesh)
  scene.add(trail)
  satellites.push({ mesh, trail, angle, height, yOffset })

  // 数量控制:超过上限就回收最早的
  while (satellites.length > SATELLITE_MAX) {
    const oldest = satellites.shift()!
    scene.remove(oldest.mesh)
    scene.remove(oldest.trail)
    oldest.mesh.geometry.dispose()
    disposeMaterial(oldest.mesh.material)
    oldest.trail.geometry.dispose()
    disposeMaterial(oldest.trail.material)
  }
}

/** 每帧推进卫星轨道 + 更新尾迹 */
function updateSatellites(dt: number) {
  const angularSpeed = (2 * Math.PI) / SATELLITE_ORBIT_PERIOD  // 弧度/秒
  for (const sat of satellites) {
    sat.angle += angularSpeed * dt
    sat.mesh.position.set(
      sat.height * Math.cos(sat.angle),
      sat.yOffset,
      sat.height * Math.sin(sat.angle)
    )
    // 尾迹:把旧点往后移,头部塞当前卫星位置
    const arr = (sat.trail.geometry.attributes.position as THREE.BufferAttribute).array as Float32Array
    for (let i = SATELLITE_TRAIL_LENGTH - 1; i > 0; i--) {
      arr[i * 3]     = arr[(i - 1) * 3]
      arr[i * 3 + 1] = arr[(i - 1) * 3 + 1]
      arr[i * 3 + 2] = arr[(i - 1) * 3 + 2]
    }
    arr[0] = sat.mesh.position.x
    arr[1] = sat.mesh.position.y
    arr[2] = sat.mesh.position.z
    sat.trail.geometry.attributes.position.needsUpdate = true
  }
}

/* ============== 流星(随机拖尾,寿命 3-4 秒) ============== */
function spawnMeteor() {
  // 起点:80-120 半径的随机球面方向
  const startAngle = Math.random() * Math.PI * 2
  const startPhi = Math.acos(2 * Math.random() - 1)
  const startDist = 80 + Math.random() * 40
  const startPos = new THREE.Vector3(
    startDist * Math.sin(startPhi) * Math.cos(startAngle),
    startDist * Math.cos(startPhi),
    startDist * Math.sin(startPhi) * Math.sin(startAngle)
  )
  // 终点:反向方向 80 半径(略加抖动避免完全对穿)
  const endAngle = startAngle + Math.PI + (Math.random() - 0.5) * 0.6
  const endPhi = startPhi + (Math.random() - 0.5) * 0.6
  const endPos = new THREE.Vector3(
    80 * Math.sin(endPhi) * Math.cos(endAngle),
    80 * Math.cos(endPhi),
    80 * Math.sin(endPhi) * Math.sin(endAngle)
  )
  const direction = endPos.clone().sub(startPos).normalize()
  const speed = METEOR_SPEED_MIN + Math.random() * (METEOR_SPEED_MAX - METEOR_SPEED_MIN)
  const velocity = direction.multiplyScalar(speed)
  const maxLife = METEOR_LIFE_MIN + Math.random() * (METEOR_LIFE_MAX - METEOR_LIFE_MIN)

  // 拖尾:30 段,初始全部填起点
  const positions: THREE.Vector3[] = []
  for (let i = 0; i < METEOR_TRAIL_LENGTH; i++) positions.push(startPos.clone())

  // 颜色:头部亮白,尾部淡(用 vertexColors)
  const colors: number[] = []
  for (let i = 0; i < METEOR_TRAIL_LENGTH; i++) {
    const t = i / (METEOR_TRAIL_LENGTH - 1)  // 0=头部,1=尾部
    const brightness = Math.pow(1 - t, 1.5)   // 头部强,尾部指数衰减
    colors.push(brightness, brightness * 0.95, brightness * 0.85)
  }

  const geo = new THREE.BufferGeometry()
  geo.setAttribute(
    'position',
    new THREE.Float32BufferAttribute(positions.flatMap(p => [p.x, p.y, p.z]), 3)
  )
  geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3))

  const mat = new THREE.LineBasicMaterial({
    vertexColors: true,
    transparent: true,
    opacity: 1.0,
    blending: THREE.AdditiveBlending,
    depthWrite: false
  })
  const line = new THREE.Line(geo, mat)
  scene.add(line)

  meteors.push({ line, positions, velocity, life: 0, maxLife })

  // 超过 3 颗就回收最早的
  while (meteors.length > METEOR_MAX) {
    const oldest = meteors.shift()!
    scene.remove(oldest.line)
    oldest.line.geometry.dispose()
    disposeMaterial(oldest.line.material)
  }
}

/** 每帧推进流星 + 寿命到期自动消失 */
function updateMeteors(dt: number) {
  for (let i = meteors.length - 1; i >= 0; i--) {
    const m = meteors[i]
    m.life += dt

    // 拖尾:FIFO 推进,头部前进一格
    for (let j = m.positions.length - 1; j > 0; j--) {
      m.positions[j].copy(m.positions[j - 1])
    }
    m.positions[0].add(m.velocity)

    // 写回 BufferGeometry
    const arr = (m.line.geometry.attributes.position as THREE.BufferAttribute).array as Float32Array
    for (let j = 0; j < m.positions.length; j++) {
      arr[j * 3]     = m.positions[j].x
      arr[j * 3 + 1] = m.positions[j].y
      arr[j * 3 + 2] = m.positions[j].z
    }
    m.line.geometry.attributes.position.needsUpdate = true

    // 寿命最后 30% 开始淡出
    if (m.life > m.maxLife * 0.7) {
      const fadeT = (m.life - m.maxLife * 0.7) / (m.maxLife * 0.3)
      ;(m.line.material as THREE.LineBasicMaterial).opacity = Math.max(0, 1 - fadeT)
    }

    // 寿命到期:移除并释放资源
    if (m.life >= m.maxLife) {
      scene.remove(m.line)
      m.line.geometry.dispose()
      disposeMaterial(m.line.material)
      meteors.splice(i, 1)
    }
  }
}

/* ============== DOM 城市标签更新(背面隐藏 + 投影位置) ============== */
function updateCityLabels(camera: THREE.Camera) {
  for (const c of cities) {
    const el = cityLabelEls[c.name]
    if (!el) continue
    const mesh = cityMeshes.find(m => m.userData?.name === c.name)
    if (!mesh) continue
    const worldPos = mesh.position.clone()
    worldPos.project(camera)
    if (worldPos.z > 0.99) {
      el.style.display = 'none'
      continue
    }
    el.style.display = 'block'
    el.style.left = `${(worldPos.x * 0.5 + 0.5) * (canvasEl.value?.clientWidth ?? 800)}px`
    el.style.top = `${(-worldPos.y * 0.5 + 0.5) * (canvasEl.value?.clientHeight ?? 600)}px`
  }
}

/* ============== 初始化 ============== */
async function init() {
  if (!canvasEl.value || !wrapEl.value) return

  const { clientWidth, clientHeight } = wrapEl.value

  /* 1. Scene + Camera + Renderer */
  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x020308)
  camera = new THREE.PerspectiveCamera(45, clientWidth / clientHeight, 0.1, 1000)
  camera.position.set(0, 30, 110)
  renderer = new THREE.WebGLRenderer({
    canvas: canvasEl.value,
    antialias: true,
    alpha: true
  })
  renderer.setSize(clientWidth, clientHeight)
  renderer.setPixelRatio(window.devicePixelRatio)
  renderer.setClearColor(0x000000, 0)

  /* 2. OrbitControls */
  controls = new OrbitControls(camera, canvasEl.value)
  controls.enableDamping = true
  controls.dampingFactor = 0.05
  controls.rotateSpeed = 0.5
  controls.zoomSpeed = 0.8
  controls.minDistance = 70
  controls.maxDistance = 250
  controls.enablePan = false
  controls.autoRotate = true
  controls.autoRotateSpeed = ROTATION_SPEED * 100

  /* 拖拽暂停 / 闲置恢复 */
  const IDLE_RESUME_MS = 3000
  controls.addEventListener('start', () => {
    controls.autoRotate = false
    if (resumeTimer) { clearTimeout(resumeTimer); resumeTimer = null }
  })
  controls.addEventListener('end', () => {
    if (resumeTimer) clearTimeout(resumeTimer)
    resumeTimer = window.setTimeout(() => {
      controls.autoRotate = true
      resumeTimer = null
    }, IDLE_RESUME_MS)
  })

  /* 加载纹理 — 优先 Three.js 官方仓库(mrdoob/three.js)稳定资源,失败再退而求其次 */
  console.log('[EarthCanvas] 加载地球贴图...')
  const EARTH_TEX_CHAIN = [
    'https://raw.githubusercontent.com/mrdoob/three.js/master/examples/textures/planets/earth_atmos_2048.jpg',
    'https://unpkg.com/three@0.160.0/examples/textures/planets/earth_atmos_2048.jpg',
    'https://raw.githubusercontent.com/turban/three-globe/master/example/img/earth-dark.jpg',
    'https://unpkg.com/three-globe@2.34.0/example/img/earth-blue-marble.jpg'
  ]
  const BUMP_TEX_CHAIN = [
    'https://raw.githubusercontent.com/mrdoob/three.js/master/examples/textures/planets/earth_normal_2048.jpg',
    'https://unpkg.com/three@0.160.0/examples/textures/planets/earth_normal_2048.jpg',
    'https://raw.githubusercontent.com/turban/three-globe/master/example/img/earth-topology.png',
    'https://unpkg.com/three-globe@2.34.0/example/img/earth-topology.png'
  ]
  const SPEC_TEX_CHAIN = [
    'https://raw.githubusercontent.com/mrdoob/three.js/master/examples/textures/planets/earth_specular_2048.jpg',
    'https://unpkg.com/three@0.160.0/examples/textures/planets/earth_specular_2048.jpg',
    'https://raw.githubusercontent.com/turban/three-globe/master/example/img/earth-water.png',
    'https://unpkg.com/three-globe@2.34.0/example/img/earth-water.png'
  ]
  const CLOUD_TEX_CHAIN = [
    'https://raw.githubusercontent.com/mrdoob/three.js/master/examples/textures/planets/earth_clouds_1024.png',
    'https://unpkg.com/three@0.160.0/examples/textures/planets/earth_clouds_1024.png',
    'https://raw.githubusercontent.com/turban/three-globe/master/example/img/earth-clouds.png',
    'https://unpkg.com/three-globe@2.34.0/example/img/earth-clouds.png'
  ]
  const NIGHT_TEX_CHAIN = [
    'https://raw.githubusercontent.com/mrdoob/three.js/master/examples/textures/planets/earth_lights_2048.png',
    'https://unpkg.com/three@0.160.0/examples/textures/planets/earth_lights_2048.png',
    'https://raw.githubusercontent.com/turban/three-globe/master/example/img/earth-night.jpg',
    'https://unpkg.com/three-globe@2.34.0/example/img/earth-night.jpg'
  ]

  const earthMap = await loadTextureChain(EARTH_TEX_CHAIN)
  if (!earthMap) throw new Error('[EarthCanvas] 所有地表贴图均失败')
  const bumpMap = await loadTextureChain(BUMP_TEX_CHAIN)
  const specMap = await loadTextureChain(SPEC_TEX_CHAIN)
  const cloudMap = await loadTextureChain(CLOUD_TEX_CHAIN)
  const nightMap = await loadTextureChain(NIGHT_TEX_CHAIN)

  /* 3. 地球 + 大气 + 云 + 城市 + 弧线 */
  earthMesh = createEarth(earthMap, bumpMap ?? undefined, specMap ?? undefined)
  scene.add(earthMesh)
  atmosphereMesh = createAtmosphere()
  scene.add(atmosphereMesh)
  if (cloudMap) {
    cloudMesh = createClouds(cloudMap)
    scene.add(cloudMesh)
  }

  /* 4. 极光(南北极,挂在 earthMesh 上,跟着地球转) */
  // 北极:位置 (0, +R+h, 0),环平躺(绕 X 转 -π/2)
  const northAurora = createAurora()
  northAurora.position.set(0, EARTH_RADIUS + AURORA_HEIGHT_ABOVE, 0)
  northAurora.rotation.x = -Math.PI / 2
  earthMesh.add(northAurora)
  auroraMeshes.push(northAurora)
  auroraMaterials.push(northAurora.material as THREE.ShaderMaterial)

  // 南极:位置 (0, -(R+h), 0),环翻转(绕 X 转 +π/2)
  const southAurora = createAurora()
  southAurora.position.set(0, -(EARTH_RADIUS + AURORA_HEIGHT_ABOVE), 0)
  southAurora.rotation.x = Math.PI / 2
  earthMesh.add(southAurora)
  auroraMeshes.push(southAurora)
  auroraMaterials.push(southAurora.material as THREE.ShaderMaterial)

  /* 5. 夜间城市灯光(叠在地球表面) */
  let nightMesh: THREE.Mesh | undefined
  if (nightMap) {
    const nightGeo = new THREE.SphereGeometry(EARTH_RADIUS * 1.012, 96, 64)
    const nightMat = new THREE.ShaderMaterial({
      uniforms: {
        nightMap: { value: nightMap },
        sunDir: { value: new THREE.Vector3(100, 50, 100).normalize() },
        nightTint: { value: new THREE.Color(0xffb24a) }
      },
      vertexShader: `
        varying vec3 vNormal;
        varying vec2 vUv;
        void main() {
          vNormal = normalize(normalMatrix * normal);
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform sampler2D nightMap;
        uniform vec3 sunDir;
        uniform vec3 nightTint;
        varying vec3 vNormal;
        varying vec2 vUv;
        void main() {
          vec3 cityLight = texture2D(nightMap, vUv).rgb * nightTint;
          float dayFactor = dot(normalize(vNormal), normalize(sunDir));
          float nightMask = 1.0 - smoothstep(-0.15, 0.15, dayFactor);
          gl_FragColor = vec4(cityLight * nightMask, nightMask);
        }
      `,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false
    })
    nightMesh = new THREE.Mesh(nightGeo, nightMat)
    earthMesh.add(nightMesh)
  }

  /* 6. 城市(Sprite 挂 scene) + 弧线 + 流光粒子 */
  cityMeshes = createCities()
  arcLines = createArcs()

  /* 7. 光照 */
  const sun = new THREE.DirectionalLight(0xffffff, SUN_LIGHT_INTENSITY)
  sun.position.set(100, 50, 100)
  scene.add(sun)
  const ambient = new THREE.AmbientLight(0xffffff, AMBIENT_LIGHT_INTENSITY)
  scene.add(ambient)

  /* 8. 星空 */
  starField = createStarField()
  scene.add(starField)

  /* 9. resize */
  resizeObserver = new ResizeObserver(handleResize)
  resizeObserver.observe(wrapEl.value)
  window.addEventListener('resize', handleResize)

  /* 10. 时间管理 */
  clock = new THREE.Clock()
  simTime = 0
  nextSatelliteTime = SATELLITE_SPAWN_INTERVAL
  nextMeteorTime = METEOR_SPAWN_MIN + Math.random() * (METEOR_SPAWN_MAX - METEOR_SPAWN_MIN)

  loading.value = false
  console.log('[EarthCanvas] 初始化完成 (12 城 / 6 弧线 / 2 极光 / 卫星/流星系统已就绪)')
}

function handleResize() {
  if (!wrapEl.value || !camera || !renderer) return
  const { clientWidth, clientHeight } = wrapEl.value
  if (clientWidth === 0 || clientHeight === 0) return
  camera.aspect = clientWidth / clientHeight
  camera.updateProjectionMatrix()
  renderer.setSize(clientWidth, clientHeight)
}

/* ============== 渲染循环 ============== */
function tick() {
  animFrameId = requestAnimationFrame(tick)
  if (!controls || !renderer || !scene || !camera || !clock) return

  const dt = Math.min(clock.getDelta(), 0.05)   // 单帧 dt 上限 50ms,防卡顿跳变
  simTime += dt

  controls.update()

  // 地球/云层旋转(地球:依赖 OrbitControls autoRotate;云层:独立叠加)
  if (cloudMesh) cloudMesh.rotation.y += CLOUD_ROTATION_SPEED

  // 清理过期的城市对冷却记录(ARC_COOLDOWN 秒之前的去掉)
  while (recentArcPairs.length > 0 && simTime - recentArcPairs[0][2] > ARC_COOLDOWN) {
    recentArcPairs.shift()
  }

  // 流光粒子(沿弧线 t 推进)
  updateFlowParticles()

  // 卫星:定时生成 + 公转
  if (simTime >= nextSatelliteTime) {
    spawnSatellite()
    nextSatelliteTime = simTime + SATELLITE_SPAWN_INTERVAL
  }
  if (satellites.length > 0) updateSatellites(dt)

  // 流星:定时生成 + 动画 + 寿命到期回收
  if (simTime >= nextMeteorTime) {
    spawnMeteor()
    nextMeteorTime = simTime + METEOR_SPAWN_MIN + Math.random() * (METEOR_SPAWN_MAX - METEOR_SPAWN_MIN)
  }
  if (meteors.length > 0) updateMeteors(dt)

  // 极光 shader time uniform(波形脉动)
  for (const mat of auroraMaterials) {
    mat.uniforms.time.value = simTime
  }

  // DOM 城市标签
  updateCityLabels(camera)

  renderer.render(scene, camera)
}

/* ============== 生命周期 ============== */
onMounted(async () => {
  try {
    await init()
    tick()
  } catch (e) {
    console.error('[EarthCanvas] 初始化失败', e)
  }
})

onBeforeUnmount(() => {
  if (animFrameId) cancelAnimationFrame(animFrameId)
  if (resizeObserver) resizeObserver.disconnect()
  if (resumeTimer) { clearTimeout(resumeTimer); resumeTimer = null }
  window.removeEventListener('resize', handleResize)

  // 清理卫星
  for (const sat of satellites) {
    scene.remove(sat.mesh)
    scene.remove(sat.trail)
    sat.mesh.geometry.dispose()
    disposeMaterial(sat.mesh.material)
    sat.trail.geometry.dispose()
    disposeMaterial(sat.trail.material)
  }
  satellites.length = 0

  // 清理流星
  for (const m of meteors) {
    scene.remove(m.line)
    m.line.geometry.dispose()
    disposeMaterial(m.line.material)
  }
  meteors.length = 0

  // 清理流光粒子
  for (const fp of arcFlowData) {
    if (fp.points.parent) fp.points.parent.remove(fp.points)
    fp.points.geometry.dispose()
    disposeMaterial(fp.points.material as THREE.Material | THREE.Material[])
  }
  arcFlowData.length = 0

  // 清理极光
  for (const a of auroraMeshes) {
    if (a.parent) a.parent.remove(a)
    a.geometry.dispose()
    disposeMaterial(a.material)
  }
  auroraMeshes.length = 0
  auroraMaterials.length = 0

  // 通用 dispose(地球/大气/云/城市 Sprite/星空)
  scene?.traverse((obj) => {
    if (obj instanceof THREE.Mesh) {
      obj.geometry?.dispose()
      const mat = obj.material
      if (mat) {
        if (Array.isArray(mat)) mat.forEach(m => m.dispose())
        else mat.dispose()
      }
    } else if (obj instanceof THREE.Line) {
      obj.geometry?.dispose()
      if (obj.material instanceof THREE.Material) obj.material.dispose()
    } else if (obj instanceof THREE.Sprite) {
      ;(obj.material as THREE.Material)?.dispose()
    } else if (obj instanceof THREE.Points) {
      obj.geometry?.dispose()
      if (obj.material instanceof THREE.Material) obj.material.dispose()
    }
  })
  renderer?.dispose()
  controls?.dispose()
  for (const k in cityLabelEls) cityLabelEls[k] = null
})
</script>

<style scoped>
.earth-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  background: radial-gradient(ellipse at center, #0a1428 0%, #020308 70%, #000000 100%);
  overflow: hidden;
  border-radius: 12px;
}
.earth-canvas {
  display: block;
  width: 100%;
  height: 100%;
  cursor: grab;
}
.earth-canvas:active { cursor: grabbing; }

.city-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 5;
}
.city-label {
  position: absolute;
  transform: translate(-50%, -150%);
  font-size: 11px;
  font-weight: 600;
  font-family: 'Inter', system-ui, sans-serif;
  letter-spacing: 0.04em;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(6px);
  border: 1px solid;
  white-space: nowrap;
  pointer-events: none;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.6);
  transition: opacity 0.3s ease;
  user-select: none;
}
.city-label::before {
  content: '';
  position: absolute;
  bottom: -4px;
  left: 50%;
  transform: translateX(-50%);
  width: 0;
  height: 0;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 4px solid currentColor;
  opacity: 0.6;
}

.loading-tip {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: #aaa;
  font-size: 13px;
  letter-spacing: 0.04em;
  display: flex;
  align-items: center;
  gap: 8px;
  z-index: 10;
  pointer-events: none;
}
.loading-tip .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #7c5cff;
  animation: pulse 1.2s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 0.3; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}
</style>