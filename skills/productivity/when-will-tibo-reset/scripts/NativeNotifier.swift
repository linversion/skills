import AppKit
import Darwin
import Foundation
import UserNotifications

final class NotificationDelegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    private let notificationTitle: String
    private let notificationBody: String
    private let statusPath: String

    init(title: String, body: String, statusPath: String) {
        self.notificationTitle = title
        self.notificationBody = body
        self.statusPath = statusPath
        super.init()
    }

    private func finish(_ status: String, exitCode: Int32) {
        do {
            try status.write(toFile: statusPath, atomically: true, encoding: .utf8)
        } catch {
            fputs("Could not write notification status: \(error)\n", stderr)
        }
        if exitCode == 0 {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                NSApp.terminate(nil)
            }
        } else {
            exit(exitCode)
        }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let center = UNUserNotificationCenter.current()
        center.delegate = self
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
            content.title = self.notificationTitle
            content.body = self.notificationBody
            content.sound = .default

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
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound])
    }
}

let arguments = CommandLine.arguments
guard arguments.count >= 4 else {
    fputs("Usage: When will Tibo reset <title> <body> <status-path>\n", stderr)
    exit(64)
}

let application = NSApplication.shared
application.setActivationPolicy(.accessory)
let delegate = NotificationDelegate(title: arguments[1], body: arguments[2], statusPath: arguments[3])
application.delegate = delegate
application.run()
