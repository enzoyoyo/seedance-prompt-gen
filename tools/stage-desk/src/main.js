import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { TransformControls } from "three/addons/controls/TransformControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const ASPECTS = [
  ["16:9", 16 / 9],
  ["9:16", 9 / 16],
  ["4:3", 4 / 3],
  ["1:1", 1],
  ["2.39:1", 2.39],
  ["4:5", 4 / 5],
];

const POSES = {
  stand: { label: "站立", hip: 0.86, rot: {} },
  walk: {
    label: "行走",
    hip: 0.86,
    rot: {
      thighL: [-32, 6, 0], shinL: [22, 0, 0],
      thighR: [26, -4, 0], shinR: [30, 0, 0],
      armL: [26, 0, 8], armR: [-22, 0, -8],
    },
  },
  run: {
    label: "跑步",
    hip: 0.82,
    rot: {
      spine: [14, 0, 0],
      thighL: [-50, 4, 0], shinL: [48, 0, 0],
      thighR: [34, -4, 0], shinR: [62, 0, 0],
      armL: [50, 0, 10], armR: [-42, 0, -10],
    },
  },
  crouch: {
    label: "半蹲",
    hip: 0.56,
    rot: {
      spine: [16, 0, 0],
      thighL: [-68, 8, 6], shinL: [86, 0, 0],
      thighR: [-68, -8, -6], shinR: [86, 0, 0],
      armL: [24, 0, 22], armR: [24, 0, -22],
    },
  },
  kneel: {
    label: "单膝跪",
    hip: 0.5,
    rot: {
      spine: [8, 0, 0],
      thighL: [-92, 4, 2], shinL: [150, 0, 0],
      thighR: [-16, -6, -4], shinR: [34, 0, 0],
      armR: [36, 0, -12],
    },
  },
  reach: {
    label: "伸手",
    hip: 0.86,
    rot: { spine: [6, 16, 0], head: [-4, 14, 0], armR: [-86, 8, -6] },
  },
  confront: {
    label: "对峙",
    hip: 0.86,
    rot: {
      thighL: [-6, 12, -10], thighR: [-6, -12, 10],
      armL: [16, 0, 52], forearmL: [78, 0, 0],
      armR: [16, 0, -52], forearmR: [78, 0, 0],
    },
  },
  lookback: {
    label: "回头",
    hip: 0.86,
    rot: { spine: [0, -26, 0], chest: [0, -22, 0], head: [-6, -36, 0], thighR: [-10, 0, 0] },
  },
  watch: {
    label: "观察",
    hip: 0.86,
    rot: { spine: [8, 18, 0], head: [-10, 22, 0], armL: [12, 0, 18], forearmL: [42, 0, 0] },
  },
};

const CLAY = [0xc2b6a4, 0x8e9a84, 0xa6846a, 0x6e7c8a, 0xb7a090];
const THIGH = 0.44;
const SHIN = 0.42;
const UPPER_ARM = 0.3;
const FOREARM = 0.26;

const viewport = document.querySelector("#viewport");
const outliner = document.querySelector("#outliner");
const inspector = document.querySelector("#inspector");
const noteEl = document.querySelector("#note");
const statusEl = document.querySelector("#status");
const nameInput = document.querySelector("#projectName");
const aspectSel = document.querySelector("#aspect");
const fovInput = document.querySelector("#fov");
const fovReadout = document.querySelector("#fovReadout");
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setClearColor(0x12110f, 1);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.NeutralToneMapping ?? THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
viewport.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x12110f);
scene.fog = new THREE.Fog(0x12110f, 16, 34);

const world = new THREE.Group();
scene.add(world);

const hemi = new THREE.HemisphereLight(0xe4d5c3, 0x2a241c, 0.95);
scene.add(hemi);
const sun = new THREE.DirectionalLight(0xfff2dc, 1.7);
sun.position.set(5.5, 9, 3.5);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.near = 0.5;
sun.shadow.camera.far = 28;
sun.shadow.camera.left = -8;
sun.shadow.camera.right = 8;
sun.shadow.camera.top = 8;
sun.shadow.camera.bottom = -8;
sun.shadow.bias = -0.0004;
scene.add(sun);

const ground = new THREE.Mesh(
  new THREE.CircleGeometry(18, 72),
  new THREE.MeshStandardMaterial({ color: 0x1a1814, roughness: 1, metalness: 0 }),
);
ground.rotation.x = -Math.PI / 2;
ground.receiveShadow = true;
scene.add(ground);
const grid = new THREE.GridHelper(24, 24, 0x3c362e, 0x2a2622);
grid.position.y = 0.002;
scene.add(grid);

const directorCam = new THREE.PerspectiveCamera(42, 1, 0.05, 200);
directorCam.position.set(3.4, 2.15, 4.6);
const orbit = new OrbitControls(directorCam, renderer.domElement);
orbit.target.set(0, 1, 0);
orbit.enableDamping = !reduceMotion;
orbit.dampingFactor = 0.08;
orbit.maxPolarAngle = Math.PI * 0.49;
orbit.minDistance = 0.4;
orbit.maxDistance = 40;
orbit.update();

const transform = new TransformControls(directorCam, renderer.domElement);
transform.setMode("translate");
transform.setSpace("world");
const transformHelper = transform.getHelper();
scene.add(transformHelper);

const box = new THREE.BoxHelper(new THREE.Object3D(), 0xc9842a);
box.visible = false;
scene.add(box);

const pathLine = new THREE.Line(
  new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3(0, 0, 0.01)]),
  new THREE.LineBasicMaterial({ color: 0xc9842a }),
);
pathLine.frustumCulled = false;
pathLine.visible = false;
scene.add(pathLine);
const pathMarks = new THREE.Group();
scene.add(pathMarks);

const nodes = new Map();
let seq = 1;
let selected = null;
let activeShotId = null;
let lookAtId = null;
let view = "director";
let pathMode = false;
let playing = false;
let playToken = 0;
let pathPoints = [];
let pendingFov = 35;
let pendingAspect = "16:9";
let shiftDown = false;
let suppressPick = false;
let restoring = false;
let panoName = "";
let panoUrl = "";
const undoStack = [];
const redoStack = [];
const gltfLoader = new GLTFLoader();
const textureLoader = new THREE.TextureLoader();

function uid(prefix) {
  return `${prefix}${seq++}`;
}

function projectName() {
  return nameInput.value.trim() || "片场";
}

function status(text) {
  statusEl.textContent = text;
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  }
  for (const child of children) node.append(child?.nodeType ? child : document.createTextNode(String(child ?? "")));
  return node;
}

function aspectValue(key) {
  return ASPECTS.find(([name]) => name === key)?.[1] ?? 16 / 9;
}

function checkpoint() {
  if (restoring) return;
  undoStack.push(JSON.stringify(serialize()));
  if (undoStack.length > 40) undoStack.shift();
  redoStack.length = 0;
}

function clayMaterial(color) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.84, metalness: 0 });
}

function addCapsule(parent, length, radius, material) {
  const mesh = new THREE.Mesh(
    new THREE.CapsuleGeometry(radius, Math.max(0.02, length - radius * 2), 3, 8),
    material,
  );
  mesh.position.y = -length / 2;
  mesh.castShadow = true;
  parent.add(mesh);
  return mesh;
}

function addJoint(parent, name, x, y, z, joints) {
  const joint = new THREE.Group();
  joint.name = name;
  joint.position.set(x, y, z);
  parent.add(joint);
  joints[name] = joint;
  return joint;
}

function buildFigure(material) {
  const joints = {};
  const hips = new THREE.Group();
  hips.name = "hips";
  joints.hips = hips;
  const pelvis = new THREE.Mesh(new THREE.SphereGeometry(0.1, 12, 10), material);
  pelvis.castShadow = true;
  hips.add(pelvis);
  const spine = addJoint(hips, "spine", 0, 0.08, 0, joints);
  addCapsule(spine, 0.32, 0.09, material).position.y = 0.16;
  const chest = addJoint(spine, "chest", 0, 0.3, 0, joints);
  const chestMesh = new THREE.Mesh(new THREE.SphereGeometry(0.13, 14, 12), material);
  chestMesh.scale.set(1.15, 0.9, 0.75);
  chestMesh.castShadow = true;
  chest.add(chestMesh);
  const head = addJoint(chest, "head", 0, 0.2, 0, joints);
  const skull = new THREE.Mesh(new THREE.SphereGeometry(0.11, 16, 14), material);
  skull.castShadow = true;
  head.add(skull);
  const nose = new THREE.Mesh(new THREE.SphereGeometry(0.025, 8, 8), material);
  nose.position.set(0, 0.01, 0.11);
  head.add(nose);

  const armL = addJoint(chest, "armL", -0.2, 0.02, 0, joints);
  addCapsule(armL, UPPER_ARM, 0.045, material);
  const forearmL = addJoint(armL, "forearmL", 0, -UPPER_ARM, 0, joints);
  addCapsule(forearmL, FOREARM, 0.038, material);
  const armR = addJoint(chest, "armR", 0.2, 0.02, 0, joints);
  addCapsule(armR, UPPER_ARM, 0.045, material);
  const forearmR = addJoint(armR, "forearmR", 0, -UPPER_ARM, 0, joints);
  addCapsule(forearmR, FOREARM, 0.038, material);

  const thighL = addJoint(hips, "thighL", -0.09, -0.02, 0, joints);
  addCapsule(thighL, THIGH, 0.06, material);
  const shinL = addJoint(thighL, "shinL", 0, -THIGH, 0, joints);
  addCapsule(shinL, SHIN, 0.048, material);
  const thighR = addJoint(hips, "thighR", 0.09, -0.02, 0, joints);
  addCapsule(thighR, THIGH, 0.06, material);
  const shinR = addJoint(thighR, "shinR", 0, -THIGH, 0, joints);
  addCapsule(shinR, SHIN, 0.048, material);
  return { hips, joints };
}

function applyPose(root, poseName) {
  const pose = POSES[poseName] || POSES.stand;
  const joints = root.userData.joints;
  for (const joint of Object.values(joints)) joint.rotation.set(0, 0, 0);
  joints.hips.position.y = pose.hip;
  for (const [name, deg] of Object.entries(pose.rot)) {
    const joint = joints[name];
    if (!joint) continue;
    joint.rotation.set(
      THREE.MathUtils.degToRad(deg[0]),
      THREE.MathUtils.degToRad(deg[1]),
      THREE.MathUtils.degToRad(deg[2]),
    );
  }
  root.userData.pose = POSES[poseName] ? poseName : "stand";
}

function nextName(prefix) {
  const used = new Set([...nodes.values()].map((node) => node.object.userData.name));
  let index = 1;
  while (used.has(`${prefix} ${index}`)) index += 1;
  return `${prefix} ${index}`;
}

function register(object, type, extra = {}) {
  const record = { type, object, ...extra };
  nodes.set(object.userData.id, record);
  return record;
}

function makeActor(parent, item = {}) {
  const id = item.id || uid("a");
  if (item.id) seq = Math.max(seq, Number(String(item.id).replace(/\D/g, "")) + 1 || seq);
  const color = item.color ?? CLAY[[...nodes.values()].filter((node) => node.type === "actor").length % CLAY.length];
  const material = clayMaterial(color);
  const root = new THREE.Group();
  const figure = buildFigure(material);
  root.add(figure.hips);
  root.userData = {
    id,
    type: "actor",
    name: item.name || nextName("角色"),
    pose: "stand",
    color,
    joints: figure.joints,
  };
  parent.add(root);
  applyPose(root, item.pose || "stand");
  if (item.position) root.position.set(item.position[0], item.position[1], item.position[2]);
  if (item.rotation) root.rotation.set(item.rotation[0], item.rotation[1], item.rotation[2]);
  if (item.scale) root.scale.set(item.scale[0], item.scale[1], item.scale[2]);
  root.visible = item.visible !== false;
  return register(root, "actor");
}

function baseGeometry(shape) {
  if (shape === "sphere") return new THREE.SphereGeometry(0.28, 20, 16);
  if (shape === "cylinder") return new THREE.CylinderGeometry(0.22, 0.22, 0.8, 16);
  return new THREE.BoxGeometry(0.6, 0.6, 0.6);
}

function restOnFloor(root, mesh) {
  root.updateMatrixWorld(true);
  const bounds = new THREE.Box3().setFromObject(mesh);
  mesh.position.y -= bounds.min.y - root.position.y;
}

function makePrimitive(shape, item = {}) {
  const id = item.id || uid("p");
  if (item.id) seq = Math.max(seq, Number(String(item.id).replace(/\D/g, "")) + 1 || seq);
  const color = item.color ?? 0x8a8175;
  const root = new THREE.Group();
  const mesh = new THREE.Mesh(baseGeometry(shape), clayMaterial(color));
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  root.add(mesh);
  root.userData = {
    id,
    type: item.type || "primitive",
    name: item.name || nextName(shape === "sphere" ? "球体" : shape === "cylinder" ? "柱体" : "方块"),
    shape,
    color,
    missing: Boolean(item.missing),
  };
  world.add(root);
  restOnFloor(root, mesh);
  if (item.position) root.position.set(item.position[0], item.position[1], item.position[2]);
  if (item.rotation) root.rotation.set(item.rotation[0], item.rotation[1], item.rotation[2]);
  if (item.scale) root.scale.set(item.scale[0], item.scale[1], item.scale[2]);
  root.visible = item.visible !== false;
  return register(root, root.userData.type);
}

function makeGroup(item = {}) {
  const id = item.id || uid("g");
  if (item.id) seq = Math.max(seq, Number(String(item.id).replace(/\D/g, "")) + 1 || seq);
  const root = new THREE.Group();
  root.userData = { id, type: "group", name: item.name || nextName("分组") };
  world.add(root);
  if (item.position) root.position.set(item.position[0], item.position[1], item.position[2]);
  if (item.rotation) root.rotation.set(item.rotation[0], item.rotation[1], item.rotation[2]);
  if (item.scale) root.scale.set(item.scale[0], item.scale[1], item.scale[2]);
  root.visible = item.visible !== false;
  return register(root, "group");
}

function makeCamera(item = {}) {
  const id = item.id || uid("c");
  if (item.id) seq = Math.max(seq, Number(String(item.id).replace(/\D/g, "")) + 1 || seq);
  const rig = new THREE.Group();
  const aspectKey = item.aspectKey || pendingAspect;
  const fov = item.fov || pendingFov;
  const camera = new THREE.PerspectiveCamera(fov, aspectValue(aspectKey), 0.05, 12);
  camera.rotation.y = Math.PI;
  rig.add(camera);
  const body = new THREE.Mesh(
    new THREE.ConeGeometry(0.08, 0.22, 10),
    new THREE.MeshStandardMaterial({ color: 0xc9842a, roughness: 0.5, metalness: 0.05 }),
  );
  body.rotation.x = Math.PI / 2;
  rig.add(body);
  const helper = new THREE.CameraHelper(camera);
  helper.material.vertexColors = false;
  helper.material.color.set(0x5c564c);
  scene.add(helper);
  rig.userData = {
    id,
    type: "camera",
    name: item.name || nextName("机位"),
    fov,
    aspectKey,
    aspect: aspectValue(aspectKey),
  };
  world.add(rig);
  if (item.position) rig.position.set(item.position[0], item.position[1], item.position[2]);
  else {
    const direction = new THREE.Vector3();
    directorCam.getWorldDirection(direction);
    rig.position.copy(directorCam.position);
    rig.lookAt(rig.position.clone().add(direction));
  }
  if (item.rotation) rig.rotation.set(item.rotation[0], item.rotation[1], item.rotation[2]);
  if (item.scale) rig.scale.set(item.scale[0], item.scale[1], item.scale[2]);
  rig.visible = item.visible !== false;
  return register(rig, "camera", { camera, body, helper });
}

function setShotAspect(record, key) {
  record.object.userData.aspectKey = key;
  record.object.userData.aspect = aspectValue(key);
  record.camera.aspect = aspectValue(key);
  record.camera.updateProjectionMatrix();
}

function dumpNode(object) {
  const data = object.userData;
  return {
    id: data.id,
    type: data.type,
    name: data.name,
    parentId: object.parent?.userData?.id || null,
    position: object.position.toArray(),
    rotation: [object.rotation.x, object.rotation.y, object.rotation.z],
    scale: object.scale.toArray(),
    visible: object.visible,
    color: data.color,
    shape: data.shape,
    pose: data.pose,
    fov: data.fov,
    aspectKey: data.aspectKey,
    missing: data.missing || undefined,
  };
}

function serializeTree() {
  const list = [];
  const walk = (object) => {
    if (!object.userData?.id) return;
    list.push(dumpNode(object));
    for (const child of object.children) walk(child);
  };
  for (const child of world.children) walk(child);
  return list;
}

function serialize() {
  const lookAt = lookPoint().toArray();
  const tree = serializeTree().map((node) => (node.type === "camera" ? { ...node, lookAt } : node));
  return {
    version: 1,
    name: projectName(),
    exportedAt: new Date().toISOString(),
    activeShotId,
    lookAtId,
    path: pathPoints,
    panorama: panoName,
    nodes: tree,
  };
}

function disposeTree(object) {
  object.traverse((child) => {
    if (child.geometry) child.geometry.dispose();
    const materials = child.material ? [].concat(child.material) : [];
    for (const material of materials) material.dispose?.();
  });
}

function removeRecord(record) {
  if (!record) return;
  if (selected === record.object) selected = null;
  if (activeShotId === record.object.userData.id) activeShotId = null;
  if (lookAtId === record.object.userData.id) lookAtId = null;
  record.helper?.removeFromParent();
  if (record.helper) disposeTree(record.helper);
  record.object.removeFromParent();
  disposeTree(record.object);
  nodes.delete(record.object.userData.id);
}

function clearWorld() {
  transform.detach();
  for (const record of [...nodes.values()]) removeRecord(record);
  nodes.clear();
  selected = null;
  activeShotId = null;
}

function loadState(data) {
  restoring = true;
  playToken += 1;
  playing = false;
  clearWorld();
  nameInput.value = data.name || "未命名片场";
  pathPoints = Array.isArray(data.path) ? data.path.map((point) => [point[0], point[1]]) : [];
  lookAtId = data.lookAtId || null;
  let missingModel = false;
  for (const item of data.nodes || []) {
    if (item.type === "actor") makeActor(world, item);
    else if (item.type === "camera") makeCamera(item);
    else if (item.type === "group") makeGroup(item);
    else if (item.type === "model") {
      missingModel = true;
      makePrimitive(item.shape || "box", { ...item, type: "model", missing: true });
    } else makePrimitive(item.shape || "box", item);
  }
  for (const item of data.nodes || []) {
    if (!item.parentId) continue;
    const child = nodes.get(item.id)?.object;
    const parent = nodes.get(item.parentId)?.object;
    if (child && parent) parent.add(child);
  }
  activeShotId = nodes.has(data.activeShotId) ? data.activeShotId : firstCameraId();
  updatePath();
  restoring = false;
  select(nodes.get(activeShotId)?.object || world.children.find((child) => child.userData?.id) || null);
  if (missingModel) status("模型不在工程文件里，已用方块占位");
  else if (panoName) status(`全景「${panoName}」需要重新选图`);
  else status("工程已打开");
}

function firstCameraId() {
  return [...nodes.values()].find((node) => node.type === "camera")?.object.userData.id || null;
}

function kindOf(type) {
  if (type === "actor") return "人";
  if (type === "camera") return "机";
  if (type === "group") return "组";
  if (type === "model") return "模";
  return "物";
}

function refreshOutliner() {
  const scroll = outliner.scrollTop;
  outliner.replaceChildren();
  const walk = (object, depth) => {
    if (!object.userData?.id) return;
    const data = object.userData;
    const row = el("button", {
      type: "button",
      class: `row${selected === object ? " selected" : ""}${object.visible ? "" : " hidden"}`,
      "data-id": data.id,
      style: `padding-left:${10 + depth * 14}px`,
    }, [
      el("span", { class: `eye${object.visible ? " on" : ""}`, "data-eye": "1" }),
      el("span", { class: "kind" }, [kindOf(data.type)]),
      el("span", { class: "name" }, [data.name]),
    ]);
    outliner.append(row);
    for (const child of object.children) walk(child, depth + 1);
  };
  for (const child of world.children) walk(child, 0);
  outliner.scrollTop = scroll;
}

function axisValue(vector, index) {
  return [vector.x, vector.y, vector.z][index];
}

function setAxisValue(vector, index, value) {
  const key = ["x", "y", "z"][index];
  vector[key] = value;
}

function syncInspectorNumbers() {
  if (!selected) return;
  const active = document.activeElement;
  const map = [
    ["pos", selected.position],
    ["rot", selected.rotation],
    ["scl", selected.scale],
  ];
  for (const [key, vector] of map) {
    const inputs = [...inspector.querySelectorAll(`[data-vec="${key}"]`)];
    inputs.forEach((input, index) => {
      if (input === active) return;
      const raw = axisValue(vector, index);
      const value = key === "rot" ? THREE.MathUtils.radToDeg(raw) : raw;
      input.value = value.toFixed(key === "rot" ? 1 : 2);
    });
  }
}

function refreshInspector() {
  inspector.replaceChildren();
  const look = el("select", { id: "lookAt", "aria-label": "镜头看向" }, [
    el("option", { value: "" }, ["场景中心"]),
  ]);
  for (const record of nodes.values()) {
    if (record.type === "camera") continue;
    look.append(el("option", { value: record.object.userData.id }, [record.object.userData.name]));
  }
  look.value = lookAtId && nodes.has(lookAtId) ? lookAtId : "";
  look.addEventListener("change", () => {
    lookAtId = look.value || null;
    refreshNote();
  });
  inspector.append(el("div", { class: "look" }, [document.createTextNode("看向"), look]));

  if (!selected) {
    inspector.append(el("p", {}, ["选中人体、道具或机位。移动 V，旋转 R，缩放 S。按住 Shift 时缩放保持等比。"]));
    return;
  }
  const data = selected.userData;
  inspector.append(el("h2", {}, [data.name]));
  const name = el("input", { type: "text", value: data.name, "aria-label": "名称" });
  name.addEventListener("change", () => {
    checkpoint();
    data.name = name.value.trim() || data.name;
    refreshOutliner();
    refreshNote();
  });
  inspector.append(el("div", { class: "field single" }, [el("span", {}, ["名称"]), name]));

  const bindVec = (key, vector, digits, toValue, fromValue) => {
    const inputs = [0, 1, 2].map((index) => {
      const input = el("input", {
        type: "number",
        step: digits >= 1 ? "1" : "0.1",
        "data-vec": key,
        value: toValue(axisValue(vector, index)).toFixed(digits),
      });
      input.addEventListener("change", () => {
        checkpoint();
        setAxisValue(vector, index, fromValue(Number(input.value)));
        refreshNote();
      });
      return input;
    });
    return el("div", { class: "field" }, [el("span", {}, [key === "pos" ? "位置" : key === "rot" ? "旋转" : "缩放"]), ...inputs]);
  };
  inspector.append(bindVec("pos", selected.position, 2, (value) => value, (value) => value));
  inspector.append(bindVec("rot", selected.rotation, 1, THREE.MathUtils.radToDeg, THREE.MathUtils.degToRad));
  inspector.append(bindVec("scl", selected.scale, 2, (value) => value, (value) => value));

  if (data.type === "actor") {
    const poses = el("div", { class: "poses" });
    for (const [key, pose] of Object.entries(POSES)) {
      poses.append(el("button", {
        type: "button",
        class: data.pose === key ? "on" : "",
        onClick: () => {
          checkpoint();
          applyPose(selected, key);
          for (const button of poses.querySelectorAll("button")) button.classList.toggle("on", button.textContent === pose.label);
          refreshNote();
        },
      }, [pose.label]));
    }
    inspector.append(poses);
  }

  if (data.type === "primitive" || data.type === "model") {
    const color = el("input", { type: "color", value: `#${data.color.toString(16).padStart(6, "0")}`, "aria-label": "颜色" });
    color.addEventListener("input", () => {
      data.color = Number.parseInt(color.value.slice(1), 16);
      selected.traverse((child) => {
        if (child.material?.color) child.material.color.set(data.color);
      });
    });
    inspector.append(el("div", { class: "field single" }, [el("span", {}, ["颜色"]), color]));
    if (data.missing) inspector.append(el("p", {}, ["这个模型上次没有一起保存，现在是占位方块。"]));
  }

  const actions = el("div", { class: "row-actions" });
  actions.append(el("button", { type: "button", onClick: duplicateSelected }, ["复制"]));
  if (data.type !== "camera") actions.append(el("button", { type: "button", onClick: groupSelected }, ["打组"]));
  if (data.type === "group") actions.append(el("button", { type: "button", onClick: ungroupSelected }, ["拆组"]));
  actions.append(el("button", { type: "button", onClick: deleteSelected }, ["删除"]));
  inspector.append(actions);
}

function refreshHeader() {
  const shot = nodes.get(activeShotId);
  const fovValue = shot ? shot.object.userData.fov : pendingFov;
  const aspectKey = shot ? shot.object.userData.aspectKey : pendingAspect;
  if (document.activeElement !== fovInput) {
    fovInput.value = String(fovValue);
    fovReadout.textContent = `${Math.round(fovValue)}°`;
  }
  if (document.activeElement !== aspectSel) aspectSel.value = aspectKey;
}

function syncGizmo() {
  const show = view === "director" && selected && !pathMode && !playing;
  if (show) transform.attach(selected);
  else transform.detach();
  transform.enabled = Boolean(show);
  transformHelper.visible = Boolean(show);
  orbit.enabled = view === "director" && !playing;
  orbit.mouseButtons.LEFT = pathMode ? -1 : THREE.MOUSE.ROTATE;
  orbit.enableRotate = !pathMode;
}

function syncCameraChrome() {
  for (const record of nodes.values()) {
    if (record.type !== "camera") continue;
    const active = record.object.userData.id === activeShotId;
    record.body.visible = view === "director" && record.object.visible;
    record.helper.visible = view === "director" && record.object.visible;
    record.helper.material.color.set(active ? 0xc9842a : 0x5c564c);
  }
}

function select(object) {
  selected = object?.userData?.id ? object : null;
  if (selected?.userData.type === "camera") activeShotId = selected.userData.id;
  refreshOutliner();
  refreshInspector();
  refreshHeader();
  refreshNote();
  syncGizmo();
  syncCameraChrome();
  layoutFrame();
}

function layoutFrame() {
  const frame = document.querySelector("#frame");
  const aspect = aspectValue(nodes.get(activeShotId)?.object.userData.aspectKey || pendingAspect);
  const width = viewport.clientWidth;
  const height = viewport.clientHeight;
  let frameWidth = width;
  let frameHeight = width / aspect;
  if (frameHeight > height) {
    frameHeight = height;
    frameWidth = height * aspect;
  }
  frame.style.width = `${frameWidth}px`;
  frame.style.height = `${frameHeight}px`;
  frame.style.left = `${(width - frameWidth) / 2}px`;
  frame.style.top = `${(height - frameHeight) / 2}px`;
}

function setView(next) {
  if (next === "camera" && !nodes.get(activeShotId)) {
    status("先加一个机位，再看机位视角");
    next = "director";
  }
  view = next;
  viewport.classList.toggle("director", view === "director");
  document.querySelector("#viewDirector").classList.toggle("on", view === "director");
  document.querySelector("#viewCamera").classList.toggle("on", view === "camera");
  syncGizmo();
  syncCameraChrome();
  layoutFrame();
}

function setTool(mode) {
  pathMode = false;
  viewport.classList.remove("path");
  document.querySelector("#pathTool").classList.remove("on");
  transform.setMode(mode);
  transform.setSpace(mode === "translate" ? "world" : "local");
  document.querySelector("#toolMove").classList.toggle("on", mode === "translate");
  document.querySelector("#toolRotate").classList.toggle("on", mode === "rotate");
  document.querySelector("#toolScale").classList.toggle("on", mode === "scale");
  syncGizmo();
  status(mode === "translate" ? "移动" : mode === "rotate" ? "旋转" : "缩放");
}

function updatePath() {
  pathMarks.clear();
  const vectors = pathPoints.map(([x, z]) => new THREE.Vector3(x, 0.04, z));
  pathLine.geometry.dispose();
  pathLine.geometry = new THREE.BufferGeometry().setFromPoints(vectors.length ? vectors : [new THREE.Vector3()]);
  pathLine.visible = vectors.length > 1;
  const markGeo = new THREE.SphereGeometry(0.045, 8, 8);
  const markMat = new THREE.MeshBasicMaterial({ color: 0xc9842a });
  for (const point of vectors) {
    const mark = new THREE.Mesh(markGeo, markMat);
    mark.position.copy(point);
    pathMarks.add(mark);
  }
  pathMarks.visible = vectors.length > 0;
}

function lookPoint() {
  const record = nodes.get(lookAtId);
  if (!record) return new THREE.Vector3(0, 1, 0);
  return new THREE.Box3().setFromObject(record.object).getCenter(new THREE.Vector3());
}

function playPath(onDone) {
  const shot = nodes.get(activeShotId);
  if (!shot) {
    status("先加一个机位");
    return;
  }
  if (pathPoints.length < 2) {
    status("至少在地面点两个路点");
    return;
  }
  checkpoint();
  const height = shot.object.position.y || 1.5;
  const curve = new THREE.CatmullRomCurve3(
    pathPoints.map(([x, z]) => new THREE.Vector3(x, height, z)),
    false,
    "catmullrom",
    0.15,
  );
  const finish = () => {
    playing = false;
    syncGizmo();
    refreshNote();
    onDone?.();
  };
  if (reduceMotion) {
    shot.object.position.copy(curve.getPoint(1));
    shot.object.lookAt(lookPoint());
    setView("camera");
    status("已切到轨迹终点");
    finish();
    return;
  }
  const token = ++playToken;
  playing = true;
  syncGizmo();
  setView("camera");
  const duration = Math.max(2200, (curve.getLength() / 1.15) * 1000);
  const start = performance.now();
  const step = (now) => {
    if (token !== playToken) return;
    const t = Math.min(1, (now - start) / duration);
    shot.object.position.copy(curve.getPoint(t));
    shot.object.lookAt(lookPoint());
    if (t < 1) requestAnimationFrame(step);
    else {
      status("走位结束");
      finish();
    }
  };
  requestAnimationFrame(step);
}

function blockingNote() {
  const shot = nodes.get(activeShotId);
  const camera = shot?.camera || directorCam;
  camera.updateMatrixWorld();
  const camPos = camera.getWorldPosition(new THREE.Vector3());
  const forward = camera.getWorldDirection(new THREE.Vector3());
  const right = new THREE.Vector3().crossVectors(forward, new THREE.Vector3(0, 1, 0)).normalize();
  const lines = [];
  lines.push(shot ? shot.object.userData.name : "导演视角");
  lines.push(`视野 ${Math.round(shot ? shot.object.userData.fov : directorCam.fov)}°`);
  lines.push(`画幅 ${shot ? shot.object.userData.aspectKey : "随窗口"}`);
  lines.push(`镜头位置 ${camPos.x.toFixed(1)}, ${camPos.y.toFixed(1)}, ${camPos.z.toFixed(1)} 米`);
  const look = nodes.get(lookAtId);
  lines.push(look ? `看向 ${look.object.userData.name}` : "看向场景中心");
  lines.push("");
  const people = [...nodes.values()].filter((node) => node.type === "actor" || node.type === "primitive" || node.type === "model");
  if (!people.length) lines.push("空间里还没有角色或道具。");
  for (const record of people) {
    const pos = record.object.getWorldPosition(new THREE.Vector3());
    const toObject = pos.clone().sub(camPos);
    const side = toObject.dot(right);
    const depth = toObject.dot(forward);
    const sideText = Math.abs(side) < 0.15 ? "在镜头中轴" : side > 0 ? `在画面右侧 ${side.toFixed(1)} 米` : `在画面左侧 ${Math.abs(side).toFixed(1)} 米`;
    const depthText = depth >= 0 ? `前方 ${depth.toFixed(1)} 米` : `后方 ${Math.abs(depth).toFixed(1)} 米`;
    const foot = pos.y - camPos.y;
    const footText = foot > 0.15 ? `脚高于镜头 ${foot.toFixed(1)} 米` : foot < -0.15 ? `脚低于镜头 ${Math.abs(foot).toFixed(1)} 米` : "脚与镜头同高";
    const pose = record.type === "actor" ? `，${POSES[record.object.userData.pose]?.label || "站立"}` : "";
    let face = "";
    if (record.type === "actor") {
      const front = new THREE.Vector3(0, 0, 1).applyQuaternion(record.object.getWorldQuaternion(new THREE.Quaternion()));
      const towardCamera = camPos.clone().sub(pos).normalize();
      const dot = front.dot(towardCamera);
      face = dot > 0.6 ? "，面向镜头" : dot > 0.2 ? "，四分之三侧面" : dot > -0.2 ? "，正侧面" : dot > -0.6 ? "，四分之三背面" : "，背对镜头";
    }
    const parent = record.object.parent?.userData?.name;
    const group = parent ? `，属于${parent}` : "";
    lines.push(`${record.object.userData.name}${pose}${group}`);
    lines.push(`${sideText}，${depthText}，${footText}${face}`);
  }
  return lines.join("\n");
}

function refreshNote() {
  noteEl.textContent = blockingNote();
}

function downloadBlob(blob, filename) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1500);
}

async function screenshot({ copyNote = true } = {}) {
  const shot = nodes.get(activeShotId);
  const camera = shot ? shot.camera : directorCam;
  const aspect = shot ? shot.object.userData.aspect : camera.aspect;
  const longEdge = 1600;
  const width = aspect >= 1 ? longEdge : Math.round(longEdge * aspect);
  const height = aspect >= 1 ? Math.round(longEdge / aspect) : longEdge;
  const previousAspect = camera.aspect;
  camera.aspect = aspect;
  camera.updateProjectionMatrix();
  const hidden = [];
  const hide = (object) => {
    hidden.push([object, object.visible]);
    object.visible = false;
  };
  hide(transformHelper);
  hide(box);
  hide(pathLine);
  hide(pathMarks);
  for (const record of nodes.values()) {
    if (record.type !== "camera") continue;
    hide(record.body);
    hide(record.helper);
  }
  const target = new THREE.WebGLRenderTarget(width, height, { samples: 0 });
  target.texture.colorSpace = THREE.SRGBColorSpace;
  renderer.setRenderTarget(target);
  renderer.setScissorTest(false);
  renderer.setViewport(0, 0, width, height);
  renderer.render(scene, camera);
  const buffer = new Uint8Array(width * height * 4);
  await renderer.readRenderTargetPixelsAsync(target, 0, 0, width, height, buffer);
  renderer.setRenderTarget(null);
  target.dispose();
  camera.aspect = previousAspect;
  camera.updateProjectionMatrix();
  for (const [object, visible] of hidden) object.visible = visible;
  resize();

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  const image = context.createImageData(width, height);
  for (let y = 0; y < height; y += 1) {
    const row = (height - 1 - y) * width * 4;
    image.data.set(buffer.subarray(row, row + width * 4), y * width * 4);
  }
  context.putImageData(image, 0, 0);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  if (!blob) {
    status("截图失败");
    return false;
  }
  const label = (shot ? shot.object.userData.name : "导演视角").replace(/\s+/g, "");
  const ratio = shot ? shot.object.userData.aspectKey.replace(":", "x") : "window";
  downloadBlob(blob, `${projectName()}-${label}-${ratio}.png`.replace(/[\\/]/g, "-"));
  const text = blockingNote();
  noteEl.textContent = text;
  if (!copyNote) return true;
  try {
    await navigator.clipboard.writeText(text);
    status("截图已保存，站位说明已复制");
  } catch {
    status("截图已保存。站位说明在右侧");
  }
  return true;
}

async function handoff() {
  const shot = nodes.get(activeShotId);
  if (!shot) {
    status("先加一个机位，再交接");
    return;
  }
  const base = `${projectName()}-${shot.object.userData.name.replace(/\s+/g, "")}`.replace(/[\\/]/g, "-");
  downloadBlob(new Blob([JSON.stringify(serialize(), null, 2)], { type: "application/json" }), `${base}.json`);
  downloadBlob(new Blob([blockingNote()], { type: "text/plain;charset=utf-8" }), `${base}-站位.txt`);
  if (await screenshot({ copyNote: false })) status("交接三件已下载：工程、截图、站位说明");
}

function deleteSelected() {
  if (!selected) return;
  checkpoint();
  const record = nodes.get(selected.userData.id);
  const kids = record.type === "group" ? [...record.object.children].filter((child) => child.userData?.id) : [];
  for (const kid of kids) record.object.parent.attach(kid);
  removeRecord(record);
  select(null);
  status("已删除");
}

function duplicateSelected() {
  if (!selected || selected.userData.type === "group") {
    status(selected?.userData.type === "group" ? "先复制组里的对象" : "先选中一个对象");
    return;
  }
  checkpoint();
  const data = dumpNode(selected);
  data.id = undefined;
  data.parentId = null;
  data.name = nextName(data.name.replace(/\s+\d+$/, "") || data.name);
  data.position = [data.position[0] + 0.6, data.position[1], data.position[2]];
  let created;
  if (data.type === "actor") created = makeActor(selected.parent || world, data);
  else if (data.type === "camera") created = makeCamera(data);
  else created = makePrimitive(data.shape || "box", data);
  if (selected.parent?.userData?.id && data.type !== "camera") selected.parent.add(created.object);
  select(created.object);
}

function groupSelected() {
  if (!selected || selected.userData.type === "camera") {
    status("机位留在清单外层");
    return;
  }
  checkpoint();
  const parent = selected.parent;
  const group = makeGroup();
  parent.add(group.object);
  group.object.position.copy(selected.position);
  group.object.quaternion.copy(selected.quaternion);
  group.object.attach(selected);
  select(group.object);
}

function ungroupSelected() {
  if (selected?.userData.type !== "group") return;
  checkpoint();
  const parent = selected.parent;
  for (const child of [...selected.children]) {
    if (child.userData?.id) parent.attach(child);
  }
  removeRecord(nodes.get(selected.userData.id));
  select(null);
}

function addActor() {
  checkpoint();
  const count = [...nodes.values()].filter((node) => node.type === "actor").length;
  const record = makeActor(world);
  record.object.position.x = count * 0.7;
  record.object.lookAt(0, 0, 6);
  select(record.object);
}

function addShape(shape) {
  checkpoint();
  const record = makePrimitive(shape);
  const count = [...nodes.values()].filter((node) => node.type === "primitive").length;
  record.object.position.x = -0.8 - count * 0.7;
  select(record.object);
}

function addCrowd() {
  checkpoint();
  const group = makeGroup({ name: nextName("群众") });
  const total = 5;
  for (let index = 0; index < total; index += 1) {
    const angle = THREE.MathUtils.lerp(-0.7, 0.7, index / (total - 1));
    const actor = makeActor(group.object, { name: `群众 ${index + 1}` });
    actor.object.position.set(Math.sin(angle) * 2.1, 0, -1.3 - Math.cos(angle) * 0.35);
    actor.object.lookAt(0, 0, 4);
  }
  select(group.object);
  status("五人弧形站位，面向正前方");
}

function togglePath() {
  pathMode = !pathMode;
  viewport.classList.toggle("path", pathMode);
  document.querySelector("#pathTool").classList.toggle("on", pathMode);
  if (pathMode) {
    document.querySelector("#toolMove").classList.remove("on");
    document.querySelector("#toolRotate").classList.remove("on");
    document.querySelector("#toolScale").classList.remove("on");
    setView("director");
    status("在地面点路点。右键还能平移，再按一次轨迹退出");
  } else {
    setTool(transform.mode || "translate");
  }
  syncGizmo();
}

function pointerNDC(event) {
  const rect = renderer.domElement.getBoundingClientRect();
  return new THREE.Vector2(
    ((event.clientX - rect.left) / rect.width) * 2 - 1,
    -((event.clientY - rect.top) / rect.height) * 2 + 1,
  );
}

function pickObject(event) {
  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(pointerNDC(event), directorCam);
  const hits = raycaster.intersectObjects(world.children, true);
  for (const hit of hits) {
    let object = hit.object;
    while (object && !object.userData?.id) object = object.parent;
    if (object?.userData?.id) return object;
  }
  return null;
}

function pickGround(event) {
  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(pointerNDC(event), directorCam);
  const point = new THREE.Vector3();
  const hit = raycaster.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), point);
  return hit ? point : null;
}

function frameSelection() {
  const target = selected || world;
  const bounds = new THREE.Box3().setFromObject(target);
  if (bounds.isEmpty()) return;
  const center = bounds.getCenter(new THREE.Vector3());
  const distance = Math.max(2.2, bounds.getSize(new THREE.Vector3()).length() * 1.2);
  orbit.target.copy(center);
  directorCam.position.copy(center).add(new THREE.Vector3(0.7, 0.45, 1).normalize().multiplyScalar(distance));
  setView("director");
}

function resize() {
  const width = Math.max(1, viewport.clientWidth);
  const height = Math.max(1, viewport.clientHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(width, height, false);
  layoutFrame();
}

let renderFailed = false;

function render() {
  requestAnimationFrame(render);
  try {
  const width = Math.max(1, viewport.clientWidth);
  const height = Math.max(1, viewport.clientHeight);
  if (view === "camera") {
    box.visible = false;
    const shot = nodes.get(activeShotId);
    if (shot) {
      const aspect = shot.object.userData.aspect;
      shot.camera.aspect = aspect;
      shot.camera.updateProjectionMatrix();
      let frameWidth = width;
      let frameHeight = width / aspect;
      if (frameHeight > height) {
        frameHeight = height;
        frameWidth = height * aspect;
      }
      const x = (width - frameWidth) / 2;
      const y = (height - frameHeight) / 2;
      const vy = height - y - frameHeight;
      renderer.setScissorTest(false);
      renderer.setViewport(0, 0, width, height);
      renderer.setClearColor(0x070706, 1);
      renderer.clear();
      renderer.setScissorTest(true);
      renderer.setViewport(x, vy, frameWidth, frameHeight);
      renderer.setScissor(x, vy, frameWidth, frameHeight);
      renderer.render(scene, shot.camera);
      renderer.setScissorTest(false);
    }
  } else {
    directorCam.aspect = width / height;
    directorCam.updateProjectionMatrix();
    renderer.setScissorTest(false);
    renderer.setViewport(0, 0, width, height);
    renderer.setClearColor(0x12110f, 1);
    renderer.render(scene, directorCam);
    if (selected) {
      box.setFromObject(selected);
      box.visible = true;
    } else box.visible = false;
  }
  for (const record of nodes.values()) {
    if (record.helper) record.helper.update();
  }
  orbit.update();
  } catch (error) {
    if (!renderFailed) {
      renderFailed = true;
      window.__renderError = error.stack || error.message;
      status(`画面没有画出来：${error.message}`);
      console.error(error);
    }
  }
}

function saveProject() {
  const blob = new Blob([JSON.stringify(serialize(), null, 2)], { type: "application/json" });
  downloadBlob(blob, `${projectName()}.json`);
  status("工程已保存到下载目录。模型文件不在里面");
}

function undo() {
  if (!undoStack.length) return;
  redoStack.push(JSON.stringify(serialize()));
  loadState(JSON.parse(undoStack.pop()));
  status("已撤销");
}

function redo() {
  if (!redoStack.length) return;
  undoStack.push(JSON.stringify(serialize()));
  loadState(JSON.parse(redoStack.pop()));
  status("已重做");
}

function bind() {
  for (const [key] of ASPECTS) aspectSel.append(el("option", { value: key }, [key]));
  aspectSel.value = pendingAspect;
  aspectSel.addEventListener("change", () => {
    const shot = nodes.get(activeShotId);
    if (!shot) {
      pendingAspect = aspectSel.value;
      layoutFrame();
      return;
    }
    checkpoint();
    setShotAspect(shot, aspectSel.value);
    layoutFrame();
    refreshNote();
  });
  fovInput.addEventListener("pointerdown", () => checkpoint());
  fovInput.addEventListener("input", () => {
    const value = Number(fovInput.value);
    fovReadout.textContent = `${value}°`;
    const shot = nodes.get(activeShotId);
    if (!shot) {
      pendingFov = value;
      return;
    }
    shot.object.userData.fov = value;
    shot.camera.fov = value;
    shot.camera.updateProjectionMatrix();
    refreshNote();
  });
  document.querySelector("#viewDirector").addEventListener("click", () => setView("director"));
  document.querySelector("#viewCamera").addEventListener("click", () => setView("camera"));
  document.querySelector("#toolMove").addEventListener("click", () => setTool("translate"));
  document.querySelector("#toolRotate").addEventListener("click", () => setTool("rotate"));
  document.querySelector("#toolScale").addEventListener("click", () => setTool("scale"));
  document.querySelector("#addActor").addEventListener("click", addActor);
  document.querySelector("#addBox").addEventListener("click", () => addShape("box"));
  document.querySelector("#addSphere").addEventListener("click", () => addShape("sphere"));
  document.querySelector("#addCyl").addEventListener("click", () => addShape("cylinder"));
  document.querySelector("#addCrowd").addEventListener("click", addCrowd);
  document.querySelector("#addCam").addEventListener("click", () => {
    checkpoint();
    const record = makeCamera();
    select(record.object);
    status("新机位用的是你现在的导演视角");
  });
  document.querySelector("#pathTool").addEventListener("click", togglePath);
  document.querySelector("#clearPath").addEventListener("click", () => {
    if (!pathPoints.length) return;
    checkpoint();
    pathPoints = [];
    updatePath();
    status("路点已清空");
  });
  document.querySelector("#playPath").addEventListener("click", () => playPath());
  document.querySelector("#recordPath").addEventListener("click", () => {
    if (typeof renderer.domElement.captureStream !== "function" || typeof MediaRecorder === "undefined") {
      status("这个浏览器录不了运镜，可以先走位");
      return;
    }
    const mime = ["video/webm;codecs=vp9", "video/webm"].find((type) => MediaRecorder.isTypeSupported(type));
    if (!mime) {
      status("这个浏览器没有 webm 录制");
      return;
    }
    if (reduceMotion) {
      playPath();
      status("减少动态时只切到终点，不录轨迹");
      return;
    }
    const stream = renderer.domElement.captureStream(30);
    const recorder = new MediaRecorder(stream, { mimeType: mime });
    const chunks = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size) chunks.push(event.data);
    };
    recorder.onstop = () => downloadBlob(new Blob(chunks, { type: mime }), `${projectName()}-运镜.webm`);
    recorder.start();
    playPath(() => {
      recorder.stop();
      status("运镜已保存");
    });
  });
  document.querySelector("#panoBtn").addEventListener("click", () => document.querySelector("#panoFile").click());
  document.querySelector("#panoFile").addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (panoUrl) URL.revokeObjectURL(panoUrl);
    panoUrl = URL.createObjectURL(file);
    panoName = file.name;
    textureLoader.load(panoUrl, (texture) => {
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.mapping = THREE.EquirectangularReflectionMapping;
      scene.background = texture;
      scene.fog = null;
      status("全景已铺到天幕。若原图不是 360°，地平线会对不齐");
    }, undefined, () => status("这张图打不开"));
  });
  document.querySelector("#clearPano").addEventListener("click", () => {
    scene.background = new THREE.Color(0x12110f);
    scene.fog = new THREE.Fog(0x12110f, 16, 34);
    if (panoUrl) URL.revokeObjectURL(panoUrl);
    panoUrl = "";
    panoName = "";
    status("已去掉全景");
  });
  document.querySelector("#modelBtn").addEventListener("click", () => document.querySelector("#modelFile").click());
  document.querySelector("#modelFile").addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".glb")) {
      status("请选 .glb。带外部贴图的 gltf 这次读不了");
      return;
    }
    try {
      const buffer = await file.arrayBuffer();
      gltfLoader.parse(buffer, "", (gltf) => {
        checkpoint();
        const root = new THREE.Group();
        const id = uid("m");
        root.userData = { id, type: "model", name: file.name.replace(/\.glb$/i, ""), color: 0x8a8175, shape: "box" };
        root.add(gltf.scene);
        world.add(root);
        const bounds = new THREE.Box3().setFromObject(gltf.scene);
        const height = Math.max(0.001, bounds.max.y - bounds.min.y);
        gltf.scene.scale.multiplyScalar(1.75 / height);
        const fitted = new THREE.Box3().setFromObject(gltf.scene);
        const center = fitted.getCenter(new THREE.Vector3());
        gltf.scene.position.sub(center);
        gltf.scene.position.y -= new THREE.Box3().setFromObject(gltf.scene).min.y;
        gltf.scene.traverse((child) => {
          if (child.isMesh) {
            child.castShadow = true;
            child.receiveShadow = true;
          }
        });
        register(root, "model");
        select(root);
        status("模型已放到地面，身高约 1.75 米");
      }, () => status("这个 glb 读不了"));
    } catch {
      status("模型读取失败");
    }
  });
  document.querySelector("#shotBtn").addEventListener("click", () => { screenshot().catch(() => status("截图失败")); });
  document.querySelector("#handoffBtn").addEventListener("click", () => { handoff().catch(() => status("交接失败")); });
  document.querySelector("#copyNote").addEventListener("click", async () => {
    const text = blockingNote();
    noteEl.textContent = text;
    try {
      await navigator.clipboard.writeText(text);
      status("站位说明已复制");
    } catch {
      status("复制被浏览器拦住了，右侧文字可以手动选");
    }
  });
  document.querySelector("#saveBtn").addEventListener("click", saveProject);
  document.querySelector("#loadBtn").addEventListener("click", () => document.querySelector("#loadFile").click());
  document.querySelector("#loadFile").addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      checkpoint();
      loadState(JSON.parse(await file.text()));
    } catch {
      status("这个文件不是片场工程");
    }
  });
  outliner.addEventListener("click", (event) => {
    const row = event.target.closest(".row");
    if (!row) return;
    const record = nodes.get(row.dataset.id);
    if (!record) return;
    if (event.target.closest("[data-eye]")) {
      checkpoint();
      record.object.visible = !record.object.visible;
      syncCameraChrome();
      refreshOutliner();
      refreshNote();
      return;
    }
    select(record.object);
  });

  transform.addEventListener("mouseDown", () => { suppressPick = true; });
  transform.addEventListener("dragging-changed", (event) => {
    orbit.enabled = !event.value && view === "director" && !pathMode;
    if (event.value) checkpoint();
    else refreshNote();
  });
  transform.addEventListener("objectChange", () => {
    if (shiftDown && transform.mode === "scale" && transform.object) {
      const scale = transform.object.scale;
      const axis = transform.axis || "XYZ";
      const value = axis.includes("X") ? scale.x : axis.includes("Y") ? scale.y : scale.z;
      scale.set(value, value, value);
    }
    syncInspectorNumbers();
  });

  let pointerStart = null;
  renderer.domElement.addEventListener("pointerdown", (event) => {
    pointerStart = { x: event.clientX, y: event.clientY };
  });
  renderer.domElement.addEventListener("pointerup", (event) => {
    if (!pointerStart || view !== "director") {
      pointerStart = null;
      return;
    }
    const dx = event.clientX - pointerStart.x;
    const dy = event.clientY - pointerStart.y;
    pointerStart = null;
    if (dx * dx + dy * dy > 16) return;
    if (suppressPick) {
      suppressPick = false;
      return;
    }
    if (pathMode && event.button === 0) {
      const point = pickGround(event);
      if (!point) return;
      checkpoint();
      pathPoints.push([Number(point.x.toFixed(2)), Number(point.z.toFixed(2))]);
      updatePath();
      status(`路点 ${pathPoints.length}`);
      return;
    }
    if (event.button === 0) select(pickObject(event));
  });
  renderer.domElement.addEventListener("contextmenu", (event) => event.preventDefault());

  window.addEventListener("keydown", (event) => {
    const tag = document.activeElement?.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
      if (event.key === "Escape") document.activeElement.blur();
      return;
    }
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
      event.preventDefault();
      if (event.shiftKey) redo();
      else undo();
      return;
    }
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      saveProject();
      return;
    }
    if (event.key === "Shift") shiftDown = true;
    const key = event.key.toLowerCase();
    if (key === "v") setTool("translate");
    else if (key === "r") setTool("rotate");
    else if (key === "s") setTool("scale");
    else if (key === "h") {
      if (!selected) return;
      checkpoint();
      selected.visible = !selected.visible;
      syncCameraChrome();
      refreshOutliner();
    } else if (key === "f") frameSelection();
    else if (key === "1") setView("director");
    else if (key === "2") setView("camera");
    else if (event.key === "Escape") {
      if (playing) {
        playToken += 1;
        playing = false;
        syncGizmo();
        status("已停下走位");
      } else if (pathMode) togglePath();
      else select(null);
    } else if (event.key === "Backspace" || event.key === "Delete") {
      event.preventDefault();
      if (pathMode && pathPoints.length) {
        checkpoint();
        pathPoints.pop();
        updatePath();
        status(pathPoints.length ? `路点 ${pathPoints.length}` : "路点已清空");
      } else deleteSelected();
    } else if (event.key === " " && !event.repeat) {
      event.preventDefault();
      playPath();
    }
  });
  window.addEventListener("keyup", (event) => {
    if (event.key === "Shift") shiftDown = false;
  });
  new ResizeObserver(resize).observe(viewport);
}

function start() {
  bind();
  const hero = makeActor(world, { name: "角色 1" });
  hero.object.lookAt(0, 0, 6);
  const mark = makePrimitive("box", { name: "标记" });
  mark.object.position.set(1.2, 0, -0.4);
  const shot = makeCamera({
    name: "机位 1",
    fov: 35,
    aspectKey: "16:9",
    position: [0.2, 1.5, 3.6],
  });
  shot.object.lookAt(0, 1.15, 0);
  activeShotId = shot.object.userData.id;
  lookAtId = hero.object.userData.id;
  setView("director");
  select(hero.object);
  resize();
  render();
  status("1 格 = 1 米。V 移动，R 旋转，S 缩放，2 看机位");
}

try {
  start();
  window.__stage = {
    serialize,
    note: blockingNote,
    redraw: render,
    counts() {
      const counts = {};
      for (const record of nodes.values()) counts[record.type] = (counts[record.type] || 0) + 1;
      return counts;
    },
  };
} catch (error) {
  window.__bootError = error.stack || String(error);
  status(window.__bootError.split("\n")[0]);
}
