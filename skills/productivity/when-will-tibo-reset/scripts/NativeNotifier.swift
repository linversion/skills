import AppKit
import Darwin
import Foundation
import UserNotifications

struct NotificationPayload {
    let title: String
    let body: String
    let statusPath: String
    let sourceURL: String
}

func webURL(_ value: String) -> URL? {
    guard let url = URL(string: value),
          let scheme = url.scheme?.lowercased(),
          ["https", "http"].contains(scheme),
          url.host != nil else { return nil }
    return url
}

final class NotificationDelegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    private let payload: NotificationPayload?

    init(payload: NotificationPayload?) {
        self.payload = payload
        super.init()
    }

    private func terminateSoon() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            NSApp.terminate(nil)
        }
    }

    private func finish(_ status: String, exitCode: Int32) {
        if let payload = payload {
            do {
                try status.write(toFile: payload.statusPath, atomically: true, encoding: .utf8)
            } catch {
                fputs("Could not write notification status: \(error)\n", stderr)
            }
        }
        if exitCode == 0 {
            terminateSoon()
        } else {
            exit(exitCode)
        }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        // A notification click launches the app without a new payload. Keep the
        // run loop alive long enough for the notification response to arrive.
        guard let payload = payload else {
            DispatchQueue.main.asyncAfter(deadline: .now() + 30) {
                NSApp.terminate(nil)
            }
            return
        }
        let center = UNUserNotificationCenter.current()
        center.requestAuthorization(options: [.alert, .sound]) { granted, error in
            if let error = error {
                fputs("Notification authorization failed: \(error)\n", stderr)
                self.finish("authorization-error: \(error)", exitCode: 2)
                return
            }
            guard granted else {
                fputs("Notification permission was not granted.\n", stderr)
                self.finish("permission-not-granted", exitCode: 3)
                return
            }

            let content = UNMutableNotificationContent()
            content.title = payload.title
            content.body = payload.body
            content.sound = .default
            if let url = webURL(payload.sourceURL) {
                content.userInfo["sourceURL"] = url.absoluteString
            }

            let request = UNNotificationRequest(
                identifier: UUID().uuidString,
                content: content,
                trigger: nil
            )
            center.add(request) { addError in
                if let addError = addError {
                    fputs("Notification submission failed: \(addError)\n", stderr)
                    self.finish("submission-error: \(addError)", exitCode: 4)
                    return
                }
                self.finish("submitted", exitCode: 0)
            }
        }
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let value = response.notification.request.content.userInfo["sourceURL"] as? String
        DispatchQueue.main.async {
            if response.actionIdentifier == UNNotificationDefaultActionIdentifier,
               let value = value, let url = webURL(value) {
                if !NSWorkspace.shared.open(url) {
                    fputs("Could not open notification source URL.\n", stderr)
                }
            }
            completionHandler()
            self.terminateSoon()
        }
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound])
    }
}

let arguments = CommandLine.arguments
let payload: NotificationPayload?
if arguments.count >= 4 {
    payload = NotificationPayload(
        title: arguments[1], body: arguments[2], statusPath: arguments[3],
        sourceURL: arguments.count >= 5 ? arguments[4] : ""
    )
} else {
    payload = nil
}
let application = NSApplication.shared
application.setActivationPolicy(.accessory)
let delegate = NotificationDelegate(payload: payload)
// Install the delegate before the application starts so cold-start clicks are
// delivered even when the helper exited immediately after submitting the alert.
UNUserNotificationCenter.current().delegate = delegate
application.delegate = delegate
application.run()
