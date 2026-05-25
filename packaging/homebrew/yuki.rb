cask "yuki" do
  version "0.1.0"
  sha256 :no_check  # filled at release time

  url "https://github.com/sudhanshu/yuki/releases/download/v#{version}/Yuki-#{version}.dmg"
  name "Yuki"
  desc "Jarvis-style assistant for macOS that knows you"
  homepage "https://github.com/sudhanshu/yuki"

  livecheck do
    url :url
    strategy :github_latest
  end

  depends_on macos: ">= :monterey"

  app "Yuki.app"

  zap trash: [
    "~/Library/Application Support/Yuki",
    "~/Library/Caches/Yuki",
    "~/Library/LaunchAgents/com.yuki.agent.plist",
    "~/Library/LaunchAgents/com.yuki.scheduler.plist",
    "~/Library/Preferences/com.yuki.app.plist",
  ]
end
