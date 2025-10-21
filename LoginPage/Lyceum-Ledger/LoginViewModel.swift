//
//  LoginViewModel.swift
//  Lyceum-Ledger
//
//  Created by Antoine Nguyen on 10/16/25.
//
import SwiftUI
@MainActor
class LoginViewModel: ObservableObject {
    
    // Use @Published to notify the View of any changes.
    @Published var username = ""
    @Published var password = ""
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var isLoggedIn = false
    
    // Computed property for client-side validation and disabling the button.
    var isLoginButtonDisabled: Bool {
        return username.isEmpty || password.isEmpty || isLoading
    }
    
    func loginUser() async {
        isLoading = true
        errorMessage = nil
        
        guard let url = URL(string: "https://your-server-api.com/login") else {
            errorMessage = "Invalid URL"
            isLoading = false
            return
        }
        
        let loginData = LoginRequest(username: username, password: password)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        do {
            request.httpBody = try JSONEncoder().encode(loginData)
            
            let (data, response) = try await URLSession.shared.data(for: request)
            
            guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
                throw URLError(.badServerResponse)
            }
            
            let loginResponse = try JSONDecoder().decode(LoginResponse.self, from: data)
            
            if loginResponse.success {
                print("Login successful: \(loginResponse.message)")
                isLoggedIn = true // Set to true to trigger navigation.
            } else {
                errorMessage = loginResponse.message
            }
            
        } catch {
            errorMessage = "Login failed. Please try again."
        }
        
        // This will run after the do-catch block finishes.
        isLoading = false
    }
}
