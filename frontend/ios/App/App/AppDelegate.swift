import AppTrackingTransparency
import UIKit
import Capacitor
import TikTokBusinessSDK

@UIApplicationMain
class AppDelegate: UIResponder, UIApplicationDelegate {

    var window: UIWindow?

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        // Override point for customization after application launch.
        return true
    }

    func applicationWillResignActive(_ application: UIApplication) {
        // Sent when the application is about to move from active to inactive state. This can occur for certain types of temporary interruptions (such as an incoming phone call or SMS message) or when the user quits the application and it begins the transition to the background state.
        // Use this method to pause ongoing tasks, disable timers, and invalidate graphics rendering callbacks. Games should use this method to pause the game.
    }

    func applicationDidEnterBackground(_ application: UIApplication) {
        // Use this method to release shared resources, save user data, invalidate timers, and store enough application state information to restore your application to its current state in case it is terminated later.
        // If your application supports background execution, this method is called instead of applicationWillTerminate: when the user quits.
    }

    func applicationWillEnterForeground(_ application: UIApplication) {
        // Called as part of the transition from the background to the active state; here you can undo many of the changes made on entering the background.
    }

    func applicationDidBecomeActive(_ application: UIApplication) {
        // Restart any tasks that were paused (or not yet started) while the application was inactive. If the application was previously in the background, optionally refresh the user interface.
    }

    func applicationWillTerminate(_ application: UIApplication) {
        // Called when the application is about to terminate. Save data if appropriate. See also applicationDidEnterBackground:.
    }

    func application(_ app: UIApplication, open url: URL, options: [UIApplication.OpenURLOptionsKey: Any] = [:]) -> Bool {
        // Called when the app was launched with a url. Feel free to add additional processing here,
        // but if you want the App API to support tracking app url opens, make sure to keep this call
        return ApplicationDelegateProxy.shared.application(app, open: url, options: options)
    }

    func application(_ application: UIApplication, continue userActivity: NSUserActivity, restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void) -> Bool {
        // Called when the app was launched with an activity, including Universal Links.
        // Feel free to add additional processing here, but if you want the App API to support
        // tracking app url opens, make sure to keep this call
        return ApplicationDelegateProxy.shared.application(application, continue: userActivity, restorationHandler: restorationHandler)
    }

}

/// Root view controller. Exists only to register app-local Capacitor plugins;
/// Main.storyboard points at this class instead of CAPBridgeViewController.
class MainViewController: CAPBridgeViewController {
    override open func capacitorDidLoad() {
        bridge?.registerPluginInstance(TikTokEventsPlugin())
    }
}

/// TikTok App Events (TikTokBusinessSDK pod) — JS side is src/lib/tiktokEvents.js.
/// Nothing here runs unless JS calls `start`, which it only does when a
/// REACT_APP_TIKTOK_APP_SECRET_IOS value was present at build time.
@objc(TikTokEventsPlugin)
public class TikTokEventsPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "TikTokEventsPlugin"
    public let jsName = "TikTokEvents"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "start", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "requestTracking", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "track", returnType: CAPPluginReturnPromise)
    ]

    @objc func start(_ call: CAPPluginCall) {
        guard
            let accessToken = call.getString("accessToken"), !accessToken.isEmpty,
            let appId = call.getString("appId"),
            let ttAppId = call.getString("ttAppId"),
            let config = TikTokConfig(accessToken: accessToken, appId: appId, tiktokAppId: ttAppId)
        else {
            call.reject("Missing TikTok config")
            return
        }
        if call.getBool("debug") == true {
            config.enableDebugMode()
            config.setLogLevel(TikTokLogLevelDebug)
        }
        // Until the user has answered the tracking prompt, hold the first
        // upload briefly so the install event can carry their choice.
        if ATTrackingManager.trackingAuthorizationStatus == .notDetermined {
            config.setDelayForATTUserAuthorizationInSeconds(20)
        }
        TikTokBusiness.initializeSdk(config) { success, error in
            if success {
                call.resolve()
            } else {
                call.reject(error?.localizedDescription ?? "TikTok SDK init failed")
            }
        }
    }

    @objc func requestTracking(_ call: CAPPluginCall) {
        TikTokBusiness.requestTrackingAuthorization { status in
            call.resolve(["status": Int(status)])
        }
    }

    @objc func track(_ call: CAPPluginCall) {
        guard let name = call.getString("event"), !name.isEmpty else {
            call.reject("Missing event name")
            return
        }
        let event = TikTokBaseEvent(eventName: name)
        for (key, value) in call.getObject("properties") ?? [:] {
            event.addProperty(withKey: key, value: value)
        }
        TikTokBusiness.trackTTEvent(event)
        call.resolve()
    }
}
