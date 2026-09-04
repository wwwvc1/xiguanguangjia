# 4 套地球实现讨论报告 · 给后续生成智能体的统一规范

> 反馈核心:
> 1. "地球不会自己多方向转" — 当前 4 套都是单轴 Y 自转,看起来像原地晃
> 2. "也不像地球就是一颗黑球" — 没有真实大陆轮廓,贴图少或没,光照不行
>
> 本报告先逐个批评,再做技术分析,最后给出**4 套必须遵守的骨架规范**,附 Common Code Skeleton。

---

## 第一部分 · 对当前 4 套实现的批评

**先说明一个事实** — 文件名和文件内容对不上:
- `08-impeccable-精修.html` 内部 CSS 注释写的是 `09-anti-slop-strategic`
- `09-anti-slop-战略.html` 内部实际是 three.js 程序化贴球的代码(更接近"精修")
- `10-数据流-玻璃嵌套.html` 是带粒子流的 wireframe 球
- `11-deep-module-组件款.html` 是用 FBM noise 程序化大陆

下文按**文件路径**逐个点名,不看文件名标题。

### 套 A · `08-impeccable-精修.html`(实质:anti-slop,纯 SVG)

- **技术栈**:纯 SVG,**没有 three.js**,没有 Canvas 2D — 就是一张图
- **地球构成**:1 层 `<circle fill="#0d2034">` 底色 + 1 张 `<image href="https://picsum.photos/seed/worldmap-equirect/1200/600">` 经纬度展开图 + `clipPath` 裁成圆 + 1 层 `radialGradient` 球面阴影 + 1 层 `rimLight` 高光
- **大陆**:picsum 通用占位图,seed 是 `worldmap-equirect`,可能根本不是世界地图
- **节点**:**8 个城市**(Tokyo/NY/London/Sydney/Sao Paulo/Cairo/Mumbai/Cape Town),每个只有 `circle.city` 实心 + `circle.city-ring` 光圈,**没有脉冲环**
- **弧线**:**0 段**。完全没画
- **自转**:只有 `earthRot.setAttribute('transform', 'rotate(${a} 300 300)')`,**纯 Y 轴自转**,代码 `setAngle(angle + 0.06)` 每帧加 0.06°
- **惯性**:用户拖动时直接修改 `angle`,松手 2 秒后从当前角度继续自转 — **没有 damping/缓动**,看起来硬切
- **总结**:用户两条反馈**全中**。这就是个圆里放了一张 2D 图在转,**既不是 3D 球也不会多方向动**。是 4 套里最差的,但也是"Apple + Linear 克制风"的体现(无 glow 无 particle)

### 套 B · `09-anti-slop-战略.html`(实质:impeccable three.js 版)

- **技术栈**:three.js (CDN `unpkg.com/three@0.160.0`)
- **地球构成**:**3 层** `SphereGeometry` — `earth` r=1.4 段数 64x48(MeshPhongMaterial + 程序化 canvas 贴图)、`atmosphere` r=1.5 段数 64x48(ShaderMaterial + Fresnel,`side: BackSide`)
- **大陆**:**Canvas 2D 程序化**(`makeEarthTexture()`)用 `ctx.beginPath()/lineTo()` 画了 7 个大陆多边形(北美/南美/欧洲/非洲/亚洲/印度/澳洲),但比例明显歪,北美 180→320 像素对应经度,纯粹示意
- **光照**:`AmbientLight 0.45 + DirectionalLight 0.9` 位置 (5,3,5),`shininess: 8` — **有真实光照**
- **节点**:**10 个城市**(北京/东京/新加坡/悉尼/迪拜/伦敦/巴黎/纽约/旧金山/圣保罗),每个 3 层:**实心 sphere** + **RingGeometry 光圈** + **脉冲环**(每帧 `scale.setScalar(1 + t * 1.5)` 扩散)
- **弧线**:**7 段大圆弧**,用 `lerpVectors + Math.sin(t*Math.PI)*0.18` 抬升弧高,`LineBasicMaterial` 紫色半透明
- **自转**:`if (!isDragging) targetRotY += 0.001` — **自动时只有 Y 轴**;拖动时 `targetRotY += dx*0.005; targetRotX += dy*0.005` 两轴都更新,但 `Math.PI/2.5` 锁住 X 不让翻过来
- **惯性**:有平滑插值 `rotY += (targetRotY - rotY) * 0.08`,相机距离 `camDist += (targetCamDist - camDist) * 0.08`,但**没有松手后的旋转动量**
- **总结**:用户第一条反馈中 50% 命中(自动自转只有 Y,看起来晃);第二条"黑球"基本规避(有 canvas 程序化大陆)。是 4 套里**最完整**的 — 城市 10 个,弧线 7 段,光照 + 大气全有,只是自动态不够"地球"

### 套 C · `10-数据流-玻璃嵌套.html`

- **技术栈**:three.js (CDN `jsdelivr.net/npm/three@0.160.0`)
- **地球构成**:**3 层 sphere**,但都是 MeshBasicMaterial — `sphereGeo` r=2 段数 64x48(纯色填充,`color: 0xe5e7eb` 或 0x141416),`wireGeo` r=2.01 段数 24x16(`wireframe: true`,绿色 0.18 不透明),`glowGeo` r=2.18 段数 64x48(`BackSide + opacity 0.06`,绿色辉光)
- **大陆**:**完全没大陆**,只有一层 wireframe 经纬网格 + 一个纯色填充球 — 用户说"黑球"指的就是它
- **节点**:**8 个城市**,每个 `SphereGeometry(0.025)` 实心点 + `RingGeometry(0.04, 0.05)` 脉冲环(每帧 `sin(pulse)*0.4` 缩放)
- **弧线**:**~7 段虚线**,`LineDashedMaterial(dashSize 0.06 gapSize 0.04)`,`computeLineDistances()` 是必须的;每对相邻城市一段
- **自转**:`earthGroup.rotation.y += rotationVel.y; earthGroup.rotation.x += rotationVel.x` — **双轴自动转**,但初始 `rotationVel = {x: 0.0015, y: 0}` 即 X 轴有一个很慢的初始角速度
- **惯性**:**真正有惯性** — 拖动时 `rotationVel = {x: dy*0.0005, y: dx*0.0005}` 记录线速度,松手后 `rotationVel.y *= 0.985` 衰减,自然过渡到 0。是 4 套里唯一有真惯性的
- **额外**:外层全屏 `<canvas id="particle-canvas">` 用 2D canvas 画粒子从城市飞向 KPI 卡(投影公式 `v.project(camera)`)
- **总结**:用户第一条反馈 **规避**(双轴 + 惯性);第二条反馈**完全命中** — 球是纯色填充,没大陆贴图。但粒子飞向 KPI 这个创意最出彩

### 套 D · `11-deep-module-组件款.html`

- **技术栈**:three.js (CDN `cdnjs.cloudflare.com/ajax/libs/three.js/0.160.0/three.min.js`)
- **地球构成**:**2 层 sphere** — `earth` r=1 段数 96x96(**ShaderMaterial**,自定义片元着色器用 hash + value noise + 5 次 fbm 算陆地),`atmo` r=1.06 段数 64x64(ShaderMaterial + Fresnel + BackSide)
- **大陆**:**最像地球** — 程序化噪声生成的陆地,有 deepOcean/shallow/coast/lowland/highland/ice 6 个色阶,按 `smoothstep(0.50, 0.58, n)` 区分海陆,`smoothstep(0.78, 0.92, lat)` 加极地冰盖,有方向光 `dot(vNormal, lightDir)` 真实打光,`rim = pow(1 - abs(dot(N, Z)), 1.5)` 加蓝色边光
- **光照**:**直接在片元着色器里算**,`ambient = 0.35`,`diff * 0.75`,不需要 Three.js 灯光
- **节点**:**6 个城市**(上海/北京/旧金山/伦敦/东京/新加坡),`SphereGeometry(0.014)` 实心 + `RingGeometry(0.020, 0.028)` 脉冲环(每帧 `1 + Math.sin(t + i) * 0.3` 缩放)+ **Sprite 标签**(Canvas 2D 画 "SHA/BJS" 等文字)
- **弧线**:**0 段**(这是它的短板)
- **自转**:`if (this.autoRotate) this.userRotY += 0.0015` — **纯 Y 轴自转**;拖动也只 `this.userRotY += dx*0.005`,**完全没有 X 轴**
- **惯性**:无,但有 `setRotation(deg)` 公开方法,以及 `_destroy() / _reinstantiate()` 模块卸载测试钩子
- **总结**:用户第一条反馈 **完全命中**(只 Y 轴,拖动也只 Y 轴);第二条反馈**完全规避** — FBM noise 大陆是最接近真实的。但**没弧线**是 4 套里最弱的一环

### 一句话总结表

| 套 | 文件路径 | 自转轴数 | 真实大陆 | 弧线 | 惯性 |
|---|---|---|---|---|---|
| A | 08-impeccable-精修.html | **单 Y**(SVG) | picsum 占位图 | 0 | 无 |
| B | 09-anti-slop-战略.html | 自动 Y,拖动 XY | Canvas 多边形(粗) | 7 | 有平滑插值 |
| C | 10-数据流-玻璃嵌套.html | **XY 双轴** | **没有**(纯色填充) | ~7 | **真有惯性** |
| D | 11-deep-module-组件款.html | **单 Y**(拖动也只 Y) | **FBM 噪声(最真)** | 0 | 无 |

---

## 第二部分 · 为什么"多方向转"才像地球

真实的地球不是一个孤立旋转的刚体,而是**多层运动叠加**:

1. **自转** — 23h56m 一周,绕地轴(地球公转面法向,黄道北极)。这是主项。
2. **公转** — 365.25 天绕太阳一圈。在地球上看见的是太阳位置相对黄道移动。
3. **岁差/章动** — 地轴本身在缓慢画圆(25800 年一圈),月球和太阳引力造成约 18.6 年的章动周期。
4. **极移** — 真实地极相对地表也在几米到几十米范围内晃动。

简化到 UI 地球,我们不模拟岁差/极移(精度过头),但**必须做 3 件事**:

- **三轴漂移叠加**:Y 轴主自转(快,~0.0008 rad/帧),X 轴极慢漂移(~0.0001 周期正弦),Z 轴更慢漂移(~0.00007 周期余弦)。三个频率取**互质数**避免节奏重叠,所以看起来"无规律但有节奏"
- **大气辉光跟随但自身脉动**:大气层跟着球一起转(否则球转大气不转会有穿帮),但大气 shader 的 `uTime` 单独走一个时间戳,做微弱 alpha 脉动(0.85 ↔ 1.0)
- **云层比陆地快 1.2x**:这是真实气象数据 — 大气环流平均风速 ~30 m/s,而地表平均风速才几 m/s。所以云层单独 r=1.02 球,rotation.y += 0.0010(陆地是 0.0008)

为什么"单轴 Y 自转"看起来假?因为:
- 任何陀螺仪/天体在自转时都有**进动**(陀螺效应),X/Z 必然有微小漂移
- 用户大脑对"球"有先验模型(看过 NASA 视频、地球仪、SpaceX 直播),任何少一个轴的运动都会被识别为"贴图在动"
- 简化为 XY 三轴后,**没有任何瞬间能看出这是程序控制的循环**,因为周期太不规则

为什么不要"复杂多体"?(比如真的算岁差)用户不需要科学精度,他们要的是"看上去像地球"。三个互质周期正弦叠加已经足够让人眼产生"哦这是真的"。

---

## 第三部分 · 4 套后续生成智能体的统一技术规范

下文是**强制规范** — 每套后续生成的智能体必须在此基础上加自己的风格,但骨架一致。

### 3.1 强制 4 层地球结构(任何套都不许少)

```js
// L1: 海洋 r=1
const ocean = new THREE.Mesh(
  new THREE.SphereGeometry(1, 64, 48),
  new THREE.MeshBasicMaterial({ color: 0x0a1f3d })  // 深蓝
);

// L2: 陆地 r=1.001(略大于海避免 z-fighting)
const land = new THREE.Mesh(
  new THREE.SphereGeometry(1.001, 64, 48),
  landMaterial   // 套 B 用 Canvas 多边形,套 D 用 ShaderMaterial fbm
);

// L3: 云 r=1.02
const clouds = new THREE.Mesh(
  new THREE.SphereGeometry(1.02, 64, 48),
  new THREE.MeshBasicMaterial({
    map: cloudTexture,        // 程序化噪声灰度图
    transparent: true, opacity: 0.4
  })
);

// L4: 大气 r=1.08,BackSide,Fresnel
const atmo = new THREE.Mesh(
  new THREE.SphereGeometry(1.08, 64, 48),
  new THREE.ShaderMaterial({
    vertexShader: ..., fragmentShader: ...,  // 见下方代码骨架
    side: THREE.BackSide, blending: THREE.AdditiveBlending, transparent: true
  })
);
```

### 3.2 大陆生成(强制程序化,不许用 picsum 占位图)

**两套可选,各取所需**:

- **套 B 风格(Canvas 2D + 多边形)**:在 1024x512 canvas 上 `ctx.beginPath()/lineTo()/closePath()/fill()` 画 6 大洲(中/北美/欧亚/非洲/南美/澳洲)的近似多边形,转 `THREE.CanvasTexture`。优点:简单可控;缺点:形状粗
- **套 D 风格(片元 shader + FBM noise)**:`hash(p) + value noise + fbm 5 次`,`smoothstep(0.50, 0.58, n + 0.06*n2)` 区分海陆,6 色阶。优点:看着真;缺点:写 shader 难

**关键约束**:不管哪种,**大陆必须贴在球面**(用 `latLngToVec3` 把经纬度投到 3D 坐标,**不能当 2D 多边形画完事** — 用户看的是球,大陆要"在球上")。色阶按纬度分:赤道 `#2d5a2d`、中纬 `#1a4a1a`、高纬 `#3a3a1a`、极冰 `#d8e8f0`。

### 3.3 三轴自转(强制,直接解决"不会多方向转")

```js
const now = performance.now();
earth.rotation.y += 0.0008;                                    // Y 主轴,快
earth.rotation.x = Math.sin(now * 0.0001) * 0.1;               // X 极慢漂
earth.rotation.z = Math.cos(now * 0.00007) * 0.05;             // Z 更慢漂
clouds.rotation.y += 0.0010;                                    // 云层比陆地快 1.25x
atmo.material.uniforms.uTime.value = now * 0.001;               // 大气脉动
```

**三轴频率必须互质**(0.0001 / 0.00007 / 0.0008 取的周期是 628s / 897s / 7.85s,无最小公倍数,看起来无限不重复)。**套 D 必须改成这个**,套 A/B/C 同样替换。

### 3.4 城市节点(每套数量不同,统一规格)

- **强制**:每城市 3 层 = `SphereGeometry` 实心点 + `RingGeometry` 静态光圈 + `RingGeometry` 脉冲环(每帧缩放)
- **可选**:Sprite 标签(`THREE.SpriteMaterial + CanvasTexture` 写字)
- **经纬度 → 球面坐标工具**(强制用,见下方 Skeleton)
- **套 A**:10 城市 7 弧线(精修要密)
- **套 B**:6 城市 4 弧线(克制)
- **套 C**:8 城市 5 弧线 + 粒子流
- **套 D**:6 城市 4 弧线(沿用现在)

**夜半球处理**(可选但推荐):shader uniform `uLightDir`,计算每个城市的 `dot(normal, lightDir)`,亮度低的再加 0.5x emissive。套 D 已经在片元 shader 里支持。

### 3.5 弧线(大圆弧)

- **几何**:`lerpVectors(A, B, t)` + `normalize().multiplyScalar(R + Math.sin(t*PI)*lift)`,`lift` 取 R 的 0.15~0.25
- **材质**:`LineBasicMaterial`(轻,不要 `Line2`),`transparent + opacity: 0.32`
- **可选**:流动粒子(套 C 已经在做,从城市 1 沿线到城市 2)
- **段数**:`Math.max(20, Math.floor(dist * 30))`

### 3.6 交互(强制统一)

- **拖动**:`mousedown` → `mousemove` → `mouseup` / `touchstart` 同
- **两轴自由**:`rotationY += dx*0.005; rotationX += dy*0.005`,**X 轴不要锁**,让用户能上下翻(但限制 `-Math.PI/2 < X < Math.PI/2`)
- **滚轮缩放**:`camera.position.z = clamp(camera.position.z + deltaY * 0.003, 1.5, 5)`
- **释放后惯性**(套 C 的方式被强制采用):
  ```js
  rotationVel = { x: dy*0.0005, y: dx*0.0005 };
  // 每帧
  rotationVel.x *= 0.985; rotationVel.y *= 0.985;
  if (!isDragging) { rotation.y += rotationVel.y; rotation.x += rotationVel.x; }
  ```
- **hover tooltip**(套 C 已经在做):`Raycaster` 检测,显示玻璃 tooltip(套 D 没有,建议加)

### 3.7 性能预算(强制)

- **目标**:桌面 60 FPS,移动 30 FPS
- **SphereGeometry 段数**:`64 x 48` 足够,**不要 96**(套 D 用了 96x96 偏重,改成 64x48)
- **弧线**:`LineBasicMaterial`,**不要 `Line2`**(后者需要 LineMaterial + LineGeometry,初始化开销大)
- **城市点**:用 `Mesh`(套 B/C/D 都在用),**不要 Points**(Points 在球面上对不齐)
- **大气 shader**:**只做 Fresnel**,`pow(1 - dot(N, Z), 2.5)`,不要加 noise

### 3.8 风格差异(4 套各自特色,不可混用)

| 套 | 尺寸 | 主色 | 云层 | 弧线数 | 城市数 | 独门特色 |
|---|---|---|---|---|---|---|
| **A(精修)** | 280px | 蓝/紫(#6366f1) | 有,明显 | **7** | **10** | 玻璃信息卡嵌套,密度高 |
| **B(克制)** | 320px | Apple 蓝(#0071e3) | **无**,纯大陆 | 4 | 6 | 极简,无 glow,无 city-ring |
| **C(数据流)** | **480px** | 绿/蓝(#10b981+#3b82f6) | 有,厚重 | 5 | 8 | **粒子飞向 KPI**,wireframe 网格 |
| **D(组件款)** | 360px | 蓝紫(#818cf8) | 有,动画 | 4 | 6 | FBM 真大陆,Sprite 文字标签,可独立卸载 |

### 3.9 关键文件路径

- 当前文件:`C:\Users\wangchang\Desktop\脚本练习\个人习惯小程序\admin-web\待选web前端\08-impeccable-精修.html`(纯 SVG 必废弃或大改)
- 当前文件:`...\09-anti-slop-战略.html`(three.js 较完整,改自转轴即可)
- 当前文件:`...\10-数据流-玻璃嵌套.html`(双轴 + 惯性都对,加大陆贴图)
- 当前文件:`...\11-deep-module-组件款.html`(FBM 大陆最真,但只有 Y 轴,加 X + 弧线)
- 报告输出:`C:\Users\wangchang\Desktop\脚本练习\个人习惯小程序\admin-web\待选web前端\_DISCUSSION.md`(本文件)

---

## Common Code Skeleton · 三轴地球骨架

> 后续 4 个生成智能体直接复用,只换风格部分(颜色/贴图/城市数/弧线数)。

```js
// ============================================================
// THREE.JS COMMON SKELETON · 三轴地球骨架
// ============================================================
const R = 1;                            // 球半径(各套按尺寸缩)
// const R = 1.4;  // 套 A/B 用这个

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, w/h, 0.1, 1000);
camera.position.set(0, 0, 3.2);
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });

// --- L1 海洋 ---
const ocean = new THREE.Mesh(
  new THREE.SphereGeometry(R, 64, 48),
  new THREE.MeshBasicMaterial({ color: 0x0a1f3d })
);

// --- L2 陆地(程序化,二选一) ---
// 方案 a: Canvas 多边形(套 B)
function makeLandCanvas() {
  const c = document.createElement('canvas'); c.width = 1024; c.height = 512;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#0a1f3d'; ctx.fillRect(0,0,1024,512);
  ctx.fillStyle = '#2d5a2d';
  /* 用 beginPath/lineTo/closePath/fill 画 6 大洲,经纬度 → 像素:
     x = (lng + 180) * 1024/360
     y = (90 - lat) * 512/180 */
  return new THREE.CanvasTexture(c);
}
// 方案 b: FBM noise 片元 shader(套 D)
// 见 11-deep-module-组件款.html 的 earthFS

// --- L3 云 ---
const clouds = new THREE.Mesh(
  new THREE.SphereGeometry(R * 1.02, 64, 48),
  new THREE.MeshBasicMaterial({ map: makeCloudTexture(), transparent: true, opacity: 0.4 })
);

// --- L4 大气 ---
const atmo = new THREE.Mesh(
  new THREE.SphereGeometry(R * 1.08, 64, 48),
  new THREE.ShaderMaterial({
    vertexShader: `
      varying vec3 vN; void main() {
        vN = normalize(normalMatrix * normal);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0);
      }`,
    fragmentShader: `
      varying vec3 vN;
      uniform float uTime;
      uniform vec3 uColor;
      void main() {
        float f = pow(1.0 - abs(dot(vN, vec3(0,0,1))), 2.5);
        float pulse = 0.85 + 0.15 * sin(uTime * 0.7);
        gl_FragColor = vec4(uColor, f * pulse);
      }`,
    uniforms: { uTime: { value: 0 }, uColor: { value: new THREE.Color(0x8b5cf6) } },
    side: THREE.BackSide, blending: THREE.AdditiveBlending, transparent: true
  })
);

// --- 经纬度 → 球面坐标 ---
function latLngToVec3(lat, lng, r = R) {
  const phi = (90 - lat) * Math.PI / 180;
  const theta = (lng + 180) * Math.PI / 180;
  return new THREE.Vector3(
    -r * Math.sin(phi) * Math.cos(theta),
     r * Math.cos(phi),
     r * Math.sin(phi) * Math.sin(theta)
  );
}

// --- 城市节点(每城市 3 层) ---
const CITIES = [
  { name: '北京', lat: 39.9, lng: 116.4 },
  { name: '纽约', lat: 40.7, lng: -74.0 },
  { name: '伦敦', lat: 51.5, lng: -0.1 },
  { name: '东京', lat: 35.7, lng: 139.7 },
  { name: '悉尼', lat: -33.9, lng: 151.2 },
  { name: '巴黎', lat: 48.9, lng: 2.3 },
  { name: '迪拜', lat: 25.3, lng: 55.3 },
  { name: '旧金山', lat: 37.8, lng: -122.4 }
];
CITIES.forEach(c => {
  const pos = latLngToVec3(c.lat, c.lng, R * 1.005);
  const dot = new THREE.Mesh(
    new THREE.SphereGeometry(0.014, 12, 12),
    new THREE.MeshBasicMaterial({ color: 0xffffff })
  ); dot.position.copy(pos); earth.add(dot);
  const ring = new THREE.Mesh(
    new THREE.RingGeometry(0.020, 0.028, 24),
    new THREE.MeshBasicMaterial({ color: 0x8b5cf6, transparent:true, opacity:0.6, side:THREE.DoubleSide })
  ); ring.position.copy(pos); ring.lookAt(0,0,0); earth.add(ring);
});

// --- 大圆弧 ---
function arc(a, b, lift = 0.18) {
  const va = latLngToVec3(a.lat, a.lng, R * 1.01);
  const vb = latLngToVec3(b.lat, b.lng, R * 1.01);
  const pts = [];
  const segs = Math.max(20, Math.floor(va.distanceTo(vb) * 30));
  for (let i = 0; i <= segs; i++) {
    const t = i / segs;
    const v = new THREE.Vector3().lerpVectors(va, vb, t)
      .normalize().multiplyScalar(R * (1.01 + Math.sin(t * Math.PI) * lift));
    pts.push(v);
  }
  return new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(pts),
    new THREE.LineBasicMaterial({ color: 0x8b5cf6, transparent: true, opacity: 0.32 })
  );
}

// --- 三轴自转(关键) ---
let rotationVel = { x: 0.0001, y: 0.0008 };  // 初始带点动量
let isDragging = false, prevMouse = { x: 0, y: 0 };

function animate() {
  requestAnimationFrame(animate);
  const now = performance.now();

  // 三轴叠加,频率互质
  if (!isDragging) {
    rotationVel.y *= 0.992;                    // 衰减
    rotationVel.x *= 0.992;
    earth.rotation.y += rotationVel.y + 0.0008; // Y 主自转
    earth.rotation.x += rotationVel.x;
  }
  earth.rotation.x += Math.sin(now * 0.0001) * 0.0008;   // X 极慢漂移
  earth.rotation.z  = Math.cos(now * 0.00007) * 0.05;    // Z 更慢漂移

  // 云层比陆地快 1.25x
  clouds.rotation.y += 0.0010;

  // 大气脉动
  atmo.material.uniforms.uTime.value = now * 0.001;

  // 脉冲环
  cityMarkers.forEach((m, i) => {
    const t = (now * 0.002 + i * 0.2) % 2;
    const s = 1 + t * 1.5;
    m.ring.scale.setScalar(s);
    m.ring.material.opacity = 0.8 - t * 0.4;
  });

  renderer.render(scene, camera);
}
```

---

## 一句话行动清单

- 套 A(08)**重做**为 three.js — 纯 SVG 没救
- 套 B(09)改自转为三轴 + 城市 10 保持 + 弧线 7 保持
- 套 C(10)**加大陆贴图**(可以套 B 的 Canvas 多边形法) + 双轴惯性已对
- 套 D(11)改自转为三轴 + 加弧线 4 段 + FBM 大陆已对

文件位置:`C:\Users\wangchang\Desktop\脚本练习\个人习惯小程序\admin-web\待选web前端\_DISCUSSION.md`