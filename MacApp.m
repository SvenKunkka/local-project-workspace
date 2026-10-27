#import <Cocoa/Cocoa.h>
#import <WebKit/WebKit.h>
#import <UserNotifications/UserNotifications.h>

@interface AppDelegate : NSObject <NSApplicationDelegate, WKScriptMessageHandler, UNUserNotificationCenterDelegate>
@property NSWindow *window;
@property WKWebView *web;
@property NSTask *server;
@property NSTimer *timer;
@property NSString *base;
@property NSString *notifyBase;
@property NSString *notifyToken;
@end

@implementation AppDelegate
- (void)applicationDidFinishLaunching:(NSNotification *)note {
    NSMenu *menu=[NSMenu new]; NSMenuItem *item=[NSMenuItem new]; [menu addItem:item]; NSApp.mainMenu=menu;
    NSMenu *appMenu=[NSMenu new]; item.submenu=appMenu; [appMenu addItemWithTitle:@"返回本机工作区" action:@selector(goHome) keyEquivalent:@"h"]; [appMenu addItemWithTitle:@"退出项目工作台" action:@selector(terminate:) keyEquivalent:@"q"];
    self.window=[[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,1280,820) styleMask:NSWindowStyleMaskTitled|NSWindowStyleMaskClosable|NSWindowStyleMaskMiniaturizable|NSWindowStyleMaskResizable backing:NSBackingStoreBuffered defer:NO];
    self.window.title=@"项目工作台"; [self.window center];
    WKWebViewConfiguration *configuration=[WKWebViewConfiguration new]; [configuration.userContentController addScriptMessageHandler:self name:@"workspace"];
    self.web=[[WKWebView alloc] initWithFrame:self.window.contentView.bounds configuration:configuration]; self.web.autoresizingMask=NSViewWidthSizable|NSViewHeightSizable; self.window.contentView=self.web;
    [self.window makeKeyAndOrderFront:nil]; [NSApp activateIgnoringOtherApps:YES];
    int port=22000+arc4random_uniform(26000); self.base=[NSString stringWithFormat:@"http://127.0.0.1:%d",port];
    NSString *binary=[NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"Contents/Resources/backend/pm-server"];
    self.server=[NSTask new]; self.server.executableURL=[NSURL fileURLWithPath:binary];
    NSMutableDictionary *env=[NSProcessInfo.processInfo.environment mutableCopy]; env[@"PROJECT_MANAGER_PORT"]=[NSString stringWithFormat:@"%d",port]; env[@"NO_BROWSER"]=@"1"; self.server.environment=env;
    self.server.standardOutput=NSFileHandle.fileHandleWithNullDevice; self.server.standardError=NSFileHandle.fileHandleWithNullDevice;
    NSError *err=nil; if(![self.server launchAndReturnError:&err]){[self showError:err.localizedDescription];return;}
    [UNUserNotificationCenter currentNotificationCenter].delegate=self;
    [[UNUserNotificationCenter currentNotificationCenter] requestAuthorizationWithOptions:UNAuthorizationOptionAlert|UNAuthorizationOptionSound completionHandler:^(BOOL granted,NSError *error){}];
    [self waitForServer:0]; self.timer=[NSTimer scheduledTimerWithTimeInterval:20 target:self selector:@selector(checkReminders) userInfo:nil repeats:YES];
}
- (void)waitForServer:(int)attempt {
    if(!self.server.running){[self showError:@"本地服务未能启动，请检查应用完整性。"];return;}
    NSURL *url=[NSURL URLWithString:[self.base stringByAppendingString:@"/api/state"]];
    [[NSURLSession.sharedSession dataTaskWithURL:url completionHandler:^(NSData *data,NSURLResponse *response,NSError *error){
        dispatch_async(dispatch_get_main_queue(), ^{
            if([(NSHTTPURLResponse *)response statusCode]==200 && data){[self.web loadRequest:[NSURLRequest requestWithURL:[NSURL URLWithString:self.base]]];[self checkReminders];}
            else if(attempt<150){dispatch_after(dispatch_time(DISPATCH_TIME_NOW,200*NSEC_PER_MSEC),dispatch_get_main_queue(),^{[self waitForServer:attempt+1];});}
            else [self showError:@"本地服务启动超时。"];
        });
    }] resume];
}
- (void)checkReminders {
    [[UNUserNotificationCenter currentNotificationCenter] getNotificationSettingsWithCompletionHandler:^(UNNotificationSettings *settings){
        NSLog(@"通知授权状态：%ld",(long)settings.authorizationStatus);
        dispatch_async(dispatch_get_main_queue(),^{[self.web evaluateJavaScript:[NSString stringWithFormat:@"window.workspaceNotificationStatus=%ld;window.dispatchEvent(new Event('notification-status'))",(long)settings.authorizationStatus] completionHandler:nil];});
        if(settings.authorizationStatus!=UNAuthorizationStatusAuthorized && settings.authorizationStatus!=UNAuthorizationStatusProvisional)return;
        [self fetchDueReminders];
    }];
}
- (void)fetchDueReminders {
    NSString *base=self.notifyBase?:self.base; NSString *token=self.notifyToken;
    NSURL *url=[NSURL URLWithString:[base stringByAppendingString:@"/api/reminders-due"]];
    NSMutableURLRequest *request=[NSMutableURLRequest requestWithURL:url]; if(token.length)[request setValue:[@"Bearer " stringByAppendingString:token] forHTTPHeaderField:@"Authorization"];
    [[NSURLSession.sharedSession dataTaskWithRequest:request completionHandler:^(NSData *data,NSURLResponse *response,NSError *error){
        if(!data)return; NSArray *items=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil]; if(![items isKindOfClass:NSArray.class])return;
        for(NSDictionary *entry in items){UNMutableNotificationContent *content=[UNMutableNotificationContent new];content.title=@"任务提醒";content.body=entry[@"title"]?:@"待办任务";content.sound=UNNotificationSound.defaultSound;
            [[UNUserNotificationCenter currentNotificationCenter] addNotificationRequest:[UNNotificationRequest requestWithIdentifier:NSUUID.UUID.UUIDString content:content trigger:nil] withCompletionHandler:^(NSError *error){
                if(error){NSLog(@"系统通知提交失败：%@",error.localizedDescription);return;} NSMutableURLRequest *ack=[NSMutableURLRequest requestWithURL:[NSURL URLWithString:[base stringByAppendingString:@"/api/reminder-ack"]]];ack.HTTPMethod=@"POST";[ack setValue:@"application/json" forHTTPHeaderField:@"Content-Type"];[ack setValue:base forHTTPHeaderField:@"Origin"];if(token.length)[ack setValue:[@"Bearer " stringByAppendingString:token] forHTTPHeaderField:@"Authorization"];ack.HTTPBody=[NSJSONSerialization dataWithJSONObject:@{@"id":entry[@"id"]} options:0 error:nil];[[NSURLSession.sharedSession dataTaskWithRequest:ack] resume];
            }];}
    }] resume];
}
- (void)userContentController:(WKUserContentController *)controller didReceiveScriptMessage:(WKScriptMessage *)message {
    if(![message.body isKindOfClass:NSDictionary.class] || !message.frameInfo.mainFrame)return;
    NSURL *url=self.web.URL; if(![url.scheme isEqualToString:@"http"] || !url.host.length)return;
    self.notifyBase=[NSString stringWithFormat:@"%@://%@:%@",url.scheme,url.host,url.port?:@80];
    id token=message.body[@"token"]; self.notifyToken=[token isKindOfClass:NSString.class]?token:nil;
    [self checkReminders];
}
- (void)userNotificationCenter:(UNUserNotificationCenter *)center willPresentNotification:(UNNotification *)notification withCompletionHandler:(void (^)(UNNotificationPresentationOptions))completionHandler {completionHandler(UNNotificationPresentationOptionBanner|UNNotificationPresentationOptionSound);}
- (void)goHome {self.notifyBase=self.base;self.notifyToken=nil;[self.web loadRequest:[NSURLRequest requestWithURL:[NSURL URLWithString:self.base]]];}
- (void)showError:(NSString *)text { NSAlert *a=[NSAlert new]; a.messageText=@"项目工作台无法启动";a.informativeText=text?:@"未知错误";[a runModal]; }
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender{return YES;}
- (void)applicationWillTerminate:(NSNotification *)note{[self.timer invalidate];if(self.server.running)[self.server terminate];}
@end

int main(int argc,const char *argv[]){@autoreleasepool{NSApplication *app=NSApplication.sharedApplication;AppDelegate *delegate=[AppDelegate new];app.delegate=delegate;[app setActivationPolicy:NSApplicationActivationPolicyRegular];[app run];}return 0;}
