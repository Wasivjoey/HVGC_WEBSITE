/* Harbour View Gospel Chapel — hero background (three.js) + scroll animation (GSAP).
   Everything here is progressive enhancement: if a library fails to load or the
   visitor prefers reduced motion, the page still works and is fully readable. */
(function () {
  "use strict";
  var reduceMotion = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---- sticky nav shade on scroll ----
  var nav = document.getElementById("siteNav");
  function onScroll() {
    if (nav) { nav.classList.toggle("scrolled", window.scrollY > 40); }
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  // close mobile menu when a link is tapped
  document.querySelectorAll(".nav-links a").forEach(function (a) {
    a.addEventListener("click", function () { document.body.classList.remove("menu-open"); });
  });

  // ---------------------------------------------------------------- three.js
  function initThree() {
    if (typeof THREE === "undefined" || reduceMotion) { return; }
    var canvas = document.getElementById("bg-canvas");
    if (!canvas) { return; }

    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 100);
    camera.position.set(0, 4.5, 14);
    camera.lookAt(0, 0, 0);

    var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(window.innerWidth, window.innerHeight);

    // A grid of points forming a gently rolling "harbour" of light on water.
    var COLS = 110, ROWS = 60, GAP = 0.42;
    var count = COLS * ROWS;
    var positions = new Float32Array(count * 3);
    var base = new Float32Array(count * 2);
    var i = 0;
    for (var x = 0; x < COLS; x++) {
      for (var z = 0; z < ROWS; z++) {
        var px = (x - COLS / 2) * GAP;
        var pz = (z - ROWS / 2) * GAP;
        positions[i * 3] = px;
        positions[i * 3 + 1] = 0;
        positions[i * 3 + 2] = pz;
        base[i * 2] = px;
        base[i * 2 + 1] = pz;
        i++;
      }
    }
    var geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    var mat = new THREE.PointsMaterial({
      color: 0x2f6d92, size: 0.05, transparent: true, opacity: 0.85,
      sizeAttenuation: true, depthWrite: false,
    });
    var water = new THREE.Points(geo, mat);
    scene.add(water);

    // A few brighter "stars" rising slowly for depth.
    var sCount = 260;
    var sPos = new Float32Array(sCount * 3);
    for (var s = 0; s < sCount; s++) {
      sPos[s * 3] = (Math.random() - 0.5) * 40;
      sPos[s * 3 + 1] = Math.random() * 18;
      sPos[s * 3 + 2] = (Math.random() - 0.5) * 24 - 4;
    }
    var sGeo = new THREE.BufferGeometry();
    sGeo.setAttribute("position", new THREE.BufferAttribute(sPos, 3));
    var stars = new THREE.Points(sGeo, new THREE.PointsMaterial({
      color: 0xd9a441, size: 0.07, transparent: true, opacity: 0.75, depthWrite: false,
    }));
    scene.add(stars);

    var mouseX = 0, mouseY = 0;
    window.addEventListener("mousemove", function (e) {
      mouseX = (e.clientX / window.innerWidth - 0.5);
      mouseY = (e.clientY / window.innerHeight - 0.5);
    });

    var pos = geo.attributes.position.array;
    var clock = new THREE.Clock();
    function animate() {
      var t = clock.getElapsedTime();
      for (var k = 0; k < count; k++) {
        var bx = base[k * 2], bz = base[k * 2 + 1];
        pos[k * 3 + 1] = Math.sin(bx * 0.45 + t * 0.9) * 0.55
                       + Math.cos(bz * 0.5 + t * 0.7) * 0.45;
      }
      geo.attributes.position.needsUpdate = true;
      water.rotation.y = Math.sin(t * 0.05) * 0.08;

      // rising stars
      var sp = sGeo.attributes.position.array;
      for (var j = 0; j < sCount; j++) {
        sp[j * 3 + 1] += 0.006;
        if (sp[j * 3 + 1] > 18) { sp[j * 3 + 1] = 0; }
      }
      sGeo.attributes.position.needsUpdate = true;

      camera.position.x += (mouseX * 2.4 - camera.position.x) * 0.03;
      camera.position.y += (4.5 - mouseY * 1.6 - camera.position.y) * 0.03;
      camera.lookAt(0, 0, 0);
      renderer.render(scene, camera);
      requestAnimationFrame(animate);
    }
    animate();

    window.addEventListener("resize", function () {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    });
  }

  // ------------------------------------------------------------------- GSAP
  function initGsap() {
    if (typeof gsap === "undefined") { return; }
    document.body.classList.add("anim-ready");

    if (reduceMotion) {
      gsap.set("[data-anim], .reveal", { opacity: 1, y: 0 });
      return;
    }

    // hero entrance
    var heroItems = document.querySelectorAll("[data-anim]");
    if (heroItems.length) {
      gsap.from(heroItems, {
        opacity: 0, y: 28, duration: 1, ease: "power3.out", stagger: 0.13, delay: 0.15,
      });
    }

    // scroll reveals
    if (typeof ScrollTrigger !== "undefined") {
      gsap.registerPlugin(ScrollTrigger);
      document.querySelectorAll(".reveal").forEach(function (el) {
        gsap.fromTo(el, { opacity: 0, y: 40 }, {
          opacity: 1, y: 0, duration: 0.9, ease: "power2.out",
          scrollTrigger: { trigger: el, start: "top 88%" },
        });
      });
    } else {
      gsap.set(".reveal", { opacity: 1, y: 0 });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { initThree(); initGsap(); });
  } else {
    initThree(); initGsap();
  }
})();
