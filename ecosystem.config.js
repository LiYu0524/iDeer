module.exports = {
  apps: [
    {
      name: "daily-recommender-web",
      script: "/root/miniconda3/bin/python",
      args: "web_server.py",
      cwd: "/var/www/daily-recommender",
      interpreter: "none",
      watch: false,
      max_memory_restart: "512M",
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
  ],
};
