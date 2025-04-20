document.addEventListener("mousemove", function(e) {
    const torch = document.querySelector(".torchlight");
    torch.style.background = `radial-gradient(circle at ${e.clientX}px ${e.clientY}px, rgba(255, 255, 255, 0.7) 5%, transparent 50%)`;
});
