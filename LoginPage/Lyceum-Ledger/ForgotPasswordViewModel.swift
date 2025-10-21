//
//  ForgotPasswordViewModel.swift
//  Lyceum-Ledger
//
//  Created by Antoine Nguyen on 10/21/25.
//
import SwiftUI

@MainActor
class ForgotPasswordViewModel: ObservableObject {
    
    @Published var email = ""
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var didSendLink = false // To show a success message
    
    var isSubmitButtonDisabled: Bool {
        // You can add more complex email validation here if you want
        return email.isEmpty || isLoading
    }
    
    func sendResetLink() async {
        isLoading = true
        errorMessage = nil
        didSendLink = false
        
        // --- This is where you'd make your network call ---
        // Simulating a network call
        print("Sending password reset link to \(email)...")
        try? await Task.sleep(nanoseconds: 2_000_000_000) // 2-second delay
        
        // On a real server, you'd handle success or failure
        // For this example, we'll just assume it succeeded.
        
        isLoading = false
        didSendLink = true
        // ----------------------------------------------------
    }
}
